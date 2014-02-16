"""LInked List sparse matrix class
"""

from __future__ import division, print_function, absolute_import

__docformat__ = "restructuredtext en"

__all__ = ['lil_matrix','isspmatrix_lil']

from itertools import izip
from bisect import bisect_left, bisect_right

import numpy as np
from scipy.lib.six import xrange

from .base import spmatrix, isspmatrix
from .sputils import getdtype, isshape, issequence, isscalarlike, ismatrix, \
    IndexMixin, upcast_scalar, get_index_dtype, isintlike

from warnings import warn
from .base import SparseEfficiencyWarning
from . import _csparsetools


class lil_matrix(spmatrix, IndexMixin):
    """Row-based linked list sparse matrix

    This is an efficient structure for constructing sparse
    matrices incrementally.

    This can be instantiated in several ways:
        lil_matrix(D)
            with a dense matrix or rank-2 ndarray D

        lil_matrix(S)
            with another sparse matrix S (equivalent to S.tolil())

        lil_matrix((M, N), [dtype])
            to construct an empty matrix with shape (M, N)
            dtype is optional, defaulting to dtype='d'.

    Attributes
    ----------
    dtype : dtype
        Data type of the matrix
    shape : 2-tuple
        Shape of the matrix
    ndim : int
        Number of dimensions (this is always 2)
    nnz
        Number of nonzero elements
    data
        LIL format data array of the matrix
    rows
        LIL format row index array of the matrix

    Notes
    -----

    Sparse matrices can be used in arithmetic operations: they support
    addition, subtraction, multiplication, division, and matrix power.

    Advantages of the LIL format
        - supports flexible slicing
        - changes to the matrix sparsity structure are efficient

    Disadvantages of the LIL format
        - arithmetic operations LIL + LIL are slow (consider CSR or CSC)
        - slow column slicing (consider CSC)
        - slow matrix vector products (consider CSR or CSC)

    Intended Usage
        - LIL is a convenient format for constructing sparse matrices
        - once a matrix has been constructed, convert to CSR or
          CSC format for fast arithmetic and matrix vector operations
        - consider using the COO format when constructing large matrices

    Data Structure
        - An array (``self.rows``) of rows, each of which is a sorted
          list of column indices of non-zero elements.
        - The corresponding nonzero values are stored in similar
          fashion in ``self.data``.


    """

    def __init__(self, arg1, shape=None, dtype=None, copy=False):
        spmatrix.__init__(self)
        self.dtype = getdtype(dtype, arg1, default=float)

        # First get the shape
        if isspmatrix(arg1):
            if isspmatrix_lil(arg1) and copy:
                A = arg1.copy()
            else:
                A = arg1.tolil()

            if dtype is not None:
                A = A.astype(dtype)

            self.shape = A.shape
            self.dtype = A.dtype
            self.rows = A.rows
            self.data = A.data
        elif isinstance(arg1,tuple):
            if isshape(arg1):
                if shape is not None:
                    raise ValueError('invalid use of shape parameter')
                M, N = arg1
                self.shape = (M,N)
                self.rows = np.empty((M,), dtype=object)
                self.data = np.empty((M,), dtype=object)
                for i in range(M):
                    self.rows[i] = []
                    self.data[i] = []
            else:
                raise TypeError('unrecognized lil_matrix constructor usage')
        else:
            # assume A is dense
            try:
                A = np.asmatrix(arg1)
            except TypeError:
                raise TypeError('unsupported matrix type')
            else:
                from .csr import csr_matrix
                A = csr_matrix(A, dtype=dtype).tolil()

                self.shape = A.shape
                self.dtype = A.dtype
                self.rows = A.rows
                self.data = A.data

    def set_shape(self,shape):
        shape = tuple(shape)

        if len(shape) != 2:
            raise ValueError("Only two-dimensional sparse arrays "
                                     "are supported.")
        try:
            shape = int(shape[0]),int(shape[1])  # floats, other weirdness
        except:
            raise TypeError('invalid shape')

        if not (shape[0] >= 0 and shape[1] >= 0):
            raise ValueError('invalid shape')

        if (self._shape != shape) and (self._shape is not None):
            try:
                self = self.reshape(shape)
            except NotImplementedError:
                raise NotImplementedError("Reshaping not implemented for %s." %
                                          self.__class__.__name__)
        self._shape = shape

    shape = property(fget=spmatrix.get_shape, fset=set_shape)

    def __iadd__(self,other):
        self[:,:] = self + other
        return self

    def __isub__(self,other):
        self[:,:] = self - other
        return self

    def __imul__(self,other):
        if isscalarlike(other):
            self[:,:] = self * other
            return self
        else:
            raise NotImplementedError

    def __itruediv__(self,other):
        if isscalarlike(other):
            self[:,:] = self / other
            return self
        else:
            raise NotImplementedError

    # Whenever the dimensions change, empty lists should be created for each
    # row

    def getnnz(self, axis=None):
        """Get the count of explicitly-stored values (nonzeros)

        Parameters
        ----------
        axis : None, 0, or 1
            Select between the number of values across the whole matrix, in
            each column, or in each row.
        """
        if axis is None:
            return sum([len(rowvals) for rowvals in self.data])
        if axis < 0:
            axis += 2
        if axis == 0:
            out = np.zeros(self.shape[1])
            for row in self.rows:
                out[row] += 1
            return out
        elif axis == 1:
            return np.array([len(rowvals) for rowvals in self.data])
        else:
            raise ValueError('axis out of bounds')
    nnz = property(fget=getnnz)

    def __str__(self):
        val = ''
        for i, row in enumerate(self.rows):
            for pos, j in enumerate(row):
                val += "  %s\t%s\n" % (str((i, j)), str(self.data[i][pos]))
        return val[:-1]

    def getrowview(self, i):
        """Returns a view of the 'i'th row (without copying).
        """
        new = lil_matrix((1, self.shape[1]), dtype=self.dtype)
        new.rows[0] = self.rows[i]
        new.data[0] = self.data[i]
        return new

    def getrow(self, i):
        """Returns a copy of the 'i'th row.
        """
        if i < 0:
            i += self.shape[0]
        if i < 0 or i >= self.shape[0]:
            raise IndexError('row index out of bounds')

        new = lil_matrix((1, self.shape[1]), dtype=self.dtype)
        new.rows[0] = self.rows[i][:]
        new.data[0] = self.data[i][:]
        return new

    def _check_row_bounds(self, i):
        if i < 0:
            i += self.shape[0]
        if i < 0 or i >= self.shape[0]:
            raise IndexError('row index out of bounds')
        return i

    def _check_col_bounds(self, j):
        if j < 0:
            j += self.shape[1]
        if j < 0 or j >= self.shape[1]:
            raise IndexError('column index out of bounds')
        return j

    def __getitem__(self, index):
        """Return the element(s) index=(i, j), where j may be a slice.
        This always returns a copy for consistency, since slices into
        Python lists return copies.
        """

        # Scalar fast path first
        if isinstance(index, tuple) and len(index) == 2:
            i, j = index
            # Use isinstance checks for common index types; this is
            # ~25-50% faster than isscalarlike. Other types are
            # handled below.
            if ((isinstance(i, int) or isinstance(i, np.integer)) and
                (isinstance(j, int) or isinstance(j, np.integer))):
                v = _csparsetools.lil_get1(self.shape[0], self.shape[1],
                                           self.rows, self.data,
                                           i, j)
                return self.dtype.type(v)

        # Utilities found in IndexMixin
        i, j = self._unpack_index(index)

        # Proper check for other scalar index types
        i_intlike = isintlike(i)
        j_intlike = isintlike(j)

        if i_intlike and j_intlike:
            v = _csparsetools.lil_get1(self.shape[0], self.shape[1],
                                       self.rows, self.data,
                                       i, j)
            return self.dtype.type(v)
        elif j_intlike or isinstance(j, slice):
            # column slicing fast path
            if j_intlike:
                j = self._check_col_bounds(j)
                j = slice(j, j+1)

            if i_intlike:
                i = self._check_row_bounds(i)
                i = xrange(i, i+1)
                i_shape = None
            elif isinstance(i, slice):
                i = xrange(*i.indices(self.shape[0]))
                i_shape = None
            else:
                i = np.atleast_1d(i)
                i_shape = i.shape

            if i_shape is None or len(i_shape) == 1:
                return self._get_row_ranges(i, j)
        elif isinstance(i, slice):
            # yes, this is quite a bit faster
            return self.tocsr()[i,j].tolil()

        i, j = self._index_to_arrays(i, j)
        if i.size == 0:
            return lil_matrix(i.shape, dtype=self.dtype)

        new = lil_matrix(i.shape, dtype=self.dtype)

        i, j = _csparsetools.prepare_index_for_memoryview(i, j)
        _csparsetools.lil_fancy_get(self.shape[0], self.shape[1],
                                    self.rows, self.data,
                                    new.rows, new.data,
                                    i, j)
        return new

    def _get_row_ranges(self, rows, col_slice):
        """
        Fast path for indexing in the case where column index is slice.

        This gains performance improvement over brute force by more
        efficient skipping of zeros, by accessing the elements
        column-wise in order.

        Parameters
        ----------
        rows : sequence or xrange
            Rows indexed. If xrange, must be within valid bounds.
        col_slice : slice
            Columns indexed

        """
        j_start, j_stop, j_stride = col_slice.indices(self.shape[1])
        col_range = xrange(j_start, j_stop, j_stride)

        if not isinstance(rows, xrange):
            rows = [self._check_row_bounds(k) for k in rows]

        if j_stride == 1 and len(col_range) == self.shape[1]:
            # full row slice
            new = lil_matrix((len(rows), self.shape[1]), dtype=self.dtype)
            for nk, k in enumerate(rows):
                new.rows[nk] = self.rows[k][:]
                new.data[nk] = self.data[k][:]
            return new
        else:
            # partial row slice
            nj = len(col_range)
            new = lil_matrix((len(rows), nj), dtype=self.dtype)
            for nk, k in enumerate(rows):
                cur_row = self.rows[k]

                if j_stride > 0:
                    a = bisect_left(cur_row, j_start)
                    b = bisect_left(cur_row, j_stop)

                    if j_stride == 1:
                        new.rows[nk].extend(j - j_start for j in cur_row[a:b])
                        new.data[nk].extend(self.data[k][a:b])
                    else:
                        for j, v in izip(cur_row[a:b], self.data[k][a:b]):
                            p, r = divmod(j - j_start, j_stride)
                            if r != 0:
                                continue
                            new.rows[nk].append(p)
                            new.data[nk].append(v)
                else:
                    a = bisect_right(cur_row, j_stop)
                    b = bisect_right(cur_row, j_start)

                    for j, v in izip(cur_row[a:b], self.data[k][a:b]):
                        p, r = divmod(j - j_start, j_stride)
                        if r != 0:
                            continue
                        new.rows[nk].insert(0, p)
                        new.data[nk].insert(0, v)
                            
            return new

    def __setitem__(self, index, x):
        # Scalar fast path first
        if isinstance(index, tuple) and len(index) == 2:
            i, j = index
            # Use isinstance checks for common index types; this is
            # ~25-50% faster than isscalarlike. Scalar index
            # assignment for other types is handled below together
            # with fancy indexing.
            if ((isinstance(i, int) or isinstance(i, np.integer)) and
                (isinstance(j, int) or isinstance(j, np.integer))):
                x = self.dtype.type(x)
                if x.size > 1:
                    # Triggered if input was an ndarray
                    raise ValueError("Trying to assign a sequence to an item")
                _csparsetools.lil_insert(self.shape[0], self.shape[1],
                                         self.rows, self.data,
                                         i, j, x, self.dtype)
                return

        # General indexing
        i, j = self._unpack_index(index)

        # shortcut for common case of full matrix assign:
        if (isspmatrix(x) and isinstance(i, slice) and i == slice(None) and
                isinstance(j, slice) and j == slice(None)
                and x.shape == self.shape):
            x = lil_matrix(x, dtype=self.dtype)
            self.rows = x.rows
            self.data = x.data
            return

        i, j = self._index_to_arrays(i, j)

        if isspmatrix(x):
            x = x.toarray()

        # Make x and i into the same shape
        x = np.asarray(x, dtype=self.dtype)
        x, _ = np.broadcast_arrays(x, i)

        if x.shape != i.shape:
            raise ValueError("shape mismatch in assignment")

        # Set values
        i, j, x = _csparsetools.prepare_index_for_memoryview(i, j, x)
        _csparsetools.lil_fancy_set(self.shape[0], self.shape[1],
                                    self.rows, self.data,
                                    i, j, x)

    def _mul_scalar(self, other):
        if other == 0:
            # Multiply by zero: return the zero matrix
            new = lil_matrix(self.shape, dtype=self.dtype)
        else:
            res_dtype = upcast_scalar(self.dtype, other)

            new = self.copy()
            new = new.astype(res_dtype)
            # Multiply this scalar by every element.
            for j, rowvals in enumerate(new.data):
                new.data[j] = [val*other for val in rowvals]
        return new

    def __truediv__(self, other):           # self / other
        if isscalarlike(other):
            new = self.copy()
            # Divide every element by this scalar
            for j, rowvals in enumerate(new.data):
                new.data[j] = [val/other for val in rowvals]
            return new
        else:
            return self.tocsr() / other

    def copy(self):
        from copy import deepcopy
        new = lil_matrix(self.shape, dtype=self.dtype)
        new.data = deepcopy(self.data)
        new.rows = deepcopy(self.rows)
        return new

    def reshape(self,shape):
        new = lil_matrix(shape, dtype=self.dtype)
        j_max = self.shape[1]
        for i,row in enumerate(self.rows):
            for col,j in enumerate(row):
                new_r,new_c = np.unravel_index(i*j_max + j,shape)
                new[new_r,new_c] = self[i,j]
        return new

    def toarray(self, order=None, out=None):
        """See the docstring for `spmatrix.toarray`."""
        d = self._process_toarray_args(order, out)
        for i, row in enumerate(self.rows):
            for pos, j in enumerate(row):
                d[i, j] = self.data[i][pos]
        return d

    def transpose(self):
        return self.tocsr().transpose().tolil()

    def tolil(self, copy=False):
        if copy:
            return self.copy()
        else:
            return self

    def tocsr(self):
        """ Return Compressed Sparse Row format arrays for this matrix.
        """

        lst = [len(x) for x in self.rows]
        idx_dtype = get_index_dtype(maxval=max(self.shape[1], sum(lst)))
        indptr = np.asarray(lst, dtype=idx_dtype)
        indptr = np.concatenate((np.array([0], dtype=idx_dtype),
                                 np.cumsum(indptr, dtype=idx_dtype)))

        indices = []
        for x in self.rows:
            indices.extend(x)
        indices = np.asarray(indices, dtype=idx_dtype)

        data = []
        for x in self.data:
            data.extend(x)
        data = np.asarray(data, dtype=self.dtype)

        from .csr import csr_matrix
        return csr_matrix((data, indices, indptr), shape=self.shape)

    def tocsc(self):
        """ Return Compressed Sparse Column format arrays for this matrix.
        """
        return self.tocsr().tocsc()


def isspmatrix_lil(x):
    return isinstance(x, lil_matrix)
