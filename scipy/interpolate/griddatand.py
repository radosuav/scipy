"""
Convenience interface to N-D interpolation

.. versionadded:: 0.9

"""

import numpy as np
from interpnd import LinearNDInterpolator, NDInterpolatorBase, \
     CloughTocher2DInterpolator, _ndim_coords_from_arrays
from scipy.spatial import cKDTree

__all__ = ['griddata', 'NearestNDInterpolator', 'LinearNDInterpolator',
           'CloughTocher2DInterpolator']

#------------------------------------------------------------------------------
# Nearest-neighbour interpolation
#------------------------------------------------------------------------------

class NearestNDInterpolator(NDInterpolatorBase):
    """
    NearestNDInterpolator(points, values)

    Nearest-neighbour interpolation in N dimensions.

    .. versionadded:: 0.9

    Parameters
    ----------
    points : ndarray of floats, shape (npoints, ndims)
        Data point coordinates.
    values : ndarray of float or complex, shape (npoints, ...)
        Data values.

    Notes
    -----
    Uses ``scipy.spatial.cKDTree``

    """

    def __init__(self, x, y):
        x = _ndim_coords_from_arrays(x)
        self._check_init_shape(x, y)
        self.tree = cKDTree(x)
        self.points = x
        self.values = y

    def __call__(self, xi):
        """
        Evaluate interpolator at given points.

        Parameters
        ----------
        xi : ndarray of float, shape (..., ndim)
            Points where to interpolate data at.

        """
        xi = self._check_call_shape(xi)
        dist, i = self.tree.query(xi)
        return self.values[i]


#------------------------------------------------------------------------------
# Convenience interface function
#------------------------------------------------------------------------------

def griddata(points, values, xi, method='linear'):
    """
    griddata(points, values, xi, method='linear')

    Interpolate unstructured N-dimensional data.

    .. versionadded:: 0.9

    Parameters
    ----------
    points : ndarray of floats, shape (npoints, ndims)
        Data point coordinates. Can either be a ndarray of
        size (npoints, ndim), or a tuple of `ndim` arrays.
    values : ndarray of float or complex, shape (npoints, ...)
        Data values.
    xi : ndarray of float, shape (..., ndim)
        Points where to interpolate data at.

    method : {'linear', 'nearest', 'cubic'}
        Method of interpolation. One of

        - ``nearest``: return the value at the data point closest to
          the point of interpolation.  See `NearestNDInterpolator` for
          more details.

        - ``linear``: tesselate the input point set to n-dimensional
          simplices, and interpolate linearly on each simplex.  See
          `LinearNDInterpolator` for more details.

        - ``cubic`` (1-D): return the value detemined from a cubic
          spline.

        - ``cubic`` (2-D): return the value determined from a
          piecewise cubic, continuously differentiable (C1), and
          approximately curvature-minimizing polynomial surface. See
          `CloughTocher2DInterpolator` for more details.


    Examples
    --------

    Suppose we want to interpolate the 2-D function

    >>> def func(x, y):
    >>>     return x*(1-x)*np.cos(4*np.pi*x) * np.sin(4*np.pi*y**2)**2

    on a grid in [0, 1]x[0, 1]

    >>> grid_x, grid_y = np.mgrid[0:1:100j, 0:1:200j]

    but we only know its values at 1000 data points:

    >>> points = np.random.rand(1000, 2)
    >>> values = func(points[:,0], points[:,1])

    This can be done with `griddata` -- below we try out all of the
    interpolation methods:

    >>> from scipy.interpolate import griddata
    >>> grid_z0 = griddata(points, values, (grid_x, grid_y), method='nearest')
    >>> grid_z1 = griddata(points, values, (grid_x, grid_y), method='linear')
    >>> grid_z2 = griddata(points, values, (grid_x, grid_y), method='cubic')

    One can see that the exact result is reproduced by all of the
    methods to some degree, but for this smooth function the piecewise
    cubic interpolant gives the best results:

    >>> import matplotlib.pyplot as plt
    >>> plt.subplot(221)
    >>> plt.imshow(func(grid_x, grid_y).T, extent=(0,1,0,1), origin='lower')
    >>> plt.plot(points[:,0], points[:,1], 'k.', ms=1)
    >>> plt.title('Original')
    >>> plt.subplot(222)
    >>> plt.imshow(grid_z0.T, extent=(0,1,0,1), origin='lower')
    >>> plt.title('Nearest')
    >>> plt.subplot(223)
    >>> plt.imshow(grid_z1.T, extent=(0,1,0,1), origin='lower')
    >>> plt.title('Linear')
    >>> plt.subplot(224)
    >>> plt.imshow(grid_z2.T, extent=(0,1,0,1), origin='lower')
    >>> plt.title('Cubic')
    >>> plt.gcf().set_size_inches(6, 6)
    >>> plt.show()

    """

    points = _ndim_coords_from_arrays(points)
    xi = _ndim_coords_from_arrays(xi)

    ndim = points.shape[-1]

    if ndim == 1 and method in ('nearest', 'linear', 'cubic'):
        ip = interp1d(points, values, kind=method, axis=0, bounds_error=False)
        return ip(xi)
    elif method == 'nearest':
        ip = NearestNDInterpolator(points, values)
        return ip(xi)
    elif method == 'linear':
        ip = LinearNDInterpolator(points, values)
        return ip(xi)
    elif method == 'cubic' and ndim == 2:
        ip = CloughTocher2DInterpolator(points, values)
        return ip(xi)
    else:
        raise ValueError("Unknown interpolation method %r for "
                         "%d dimensional data" % (method, ndim))