import numpy as np
from sklearn.neighbors import KDTree
import itertools
from scipy.special import logsumexp
from sklearn.cluster import KMeans
import anndata as ad
from typing import Optional, Union, List

def mnc_correct(
    data: Union[ad.AnnData, np.ndarray],
    batch: str,
    n_neighbors: int = 5,
    n_clusters: int = 40,
    use_dims: Optional[Union[int, List[int]]] = None,
    use_rep: Optional[str] = None,
    n_iter: int = 1,
    inplace: bool = True,
) -> Optional[np.ndarray]:
    """
    A modified MNN-Correct algorithm based on cluster centroid.

    Parameters
    ----------
    data
        Matrice or AnnData object. Matrices should be shaped like n_obs x n_vars.
    batch
    n_neighbors
        Number of mutual nearest neighbors.
    n_clusters
        Number of clusters
    use_dims
    use_rep
    n_iter
    inplace

    Returns
    -------
    if `inplace=True` it updates adata with the field
    ``adata.obsm[`use_rep`_mnn]``, containing adjusted principal components.
    Otherwise, it returns the result as a numpy array.
    """
    if use_rep is None: use_rep = "X_spectral"
    mat = data.obsm[use_rep] if isinstance(data, ad.AnnData) else data
    if isinstance(use_dims, int): use_dims = range(use_dims) 
    mat = mat if use_dims is None else mat[:, use_dims]
    mat = np.asarray(mat)

    labels = data.obs[batch]
    label_uniq = list(set(labels))

    for _ in range(n_iter):
        batch_idx = []
        data_by_batch = []
        for label in label_uniq:
            idx = [i for i, x in enumerate(labels) if x == label]
            batch_idx.append(idx)
            data_by_batch.append(mat[idx,:])
        mat_ = mnc_correct_multi(data_by_batch, n_neighbors, n_clusters)
        new = np.array(mat, copy=True)
        idx = list(itertools.chain.from_iterable(batch_idx))
        for i in range(len(labels)):
            new[idx[i]] = mat_[i,:]
        mat = new

    if isinstance(data, ad.AnnData) and inplace:
        data.obsm[use_rep + "_mnn"] = mat
    else:
        return mat

def mnc_correct_multi(datas, n_neighbors, n_clusters):
    data0 = datas[0]
    for i in range(1, len(datas)):
        data1 = datas[i]
        pdata0, pdata1 = mnc_correct_pair(data0, data1, n_clusters, n_neighbors)
        ratio = data0.shape[0] / (data0.shape[0] + data1.shape[0])
        data0_ = pdata0.project(data0, weight = 1 - ratio)
        data1_ = pdata1.project(data1, weight = ratio)
        data0 = np.concatenate((data0_, data1_), axis=0)
    return data0

def mnc_correct_pair(X, Y, n_clusters, n_neighbors, random_state=0):
    n_X = X.shape[0]
    n_Y = Y.shape[0]
    c_X = KMeans(n_clusters=min(n_clusters, n_X), random_state=random_state).fit(X).cluster_centers_
    c_Y = KMeans(n_clusters=min(n_clusters, n_Y), random_state=random_state).fit(Y).cluster_centers_

    tree_X = KDTree(c_X)
    tree_Y = KDTree(c_Y)

    # X by Y matrix
    m_X = tree_Y.query(c_X, k=min(n_neighbors, n_Y), return_distance=False)

    # Y by X matrix
    m_Y_ = tree_X.query(c_Y, k=min(n_neighbors, n_X), return_distance=False)
    m_Y = []
    for i in range(m_Y_.shape[0]):
        m_Y.append(set(m_Y_[i,:]))

    i_X = []
    i_Y = []
    for i in range(m_X.shape[0]):
        for j in m_X[i]:
            if i in m_Y[j]:
                i_X.append(i)
                i_Y.append(j)
    a = c_X[i_X,:]
    b = c_Y[i_Y,:]
    return (Projector(a, b), Projector(b, a))

class Projector(object):
    def __init__(self, X, Y):
        self.reference = X
        self.vector = Y - X

    def project(self, X, weight=0.5):
        def project(x):
            P = self.reference
            U = self.vector
            d = np.sqrt(np.sum((P - x)**2, axis=1))
            w = _normalize(-(d/0.005))
            #w = 1/d
            return (x + weight * np.average(U, axis=0, weights=w))
        return np.apply_along_axis(project, 1, X)

# exp transform the weights and then normalize them to sum to 1.
def _normalize(ws):
    s = logsumexp(ws)
    return np.exp(ws - s)