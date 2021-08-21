import numpy as np  # The fundamental package for scientific computing with Python


def reciprocal_rank(rs):  # iterator of relevance scores in rank order
    """ Compute reciprocal ranks for a bunch of queries: reciprocal of the rank of the first relevant item for
    each query (considering the first element being of 'rank 1'). Relevance is binary (nonzero is relevant).

    Args:
        rs: Iterator of relevance scores (list or numpy ndarrays) in rank order (first element is the first item)
    Returns:
        Reciprocal ranks.
    """
    # for each numpy array in 'rs', take the positions of the relevant (non-zero) items
    rs = (np.asarray(r).nonzero()[0] for r in rs)
    # for each array of ranks in 'rs', if its size is 0 then the reciprocal rank is zero, otherwise it is equal to the
    # reciprocal of the rank (+1) of the first relevant item
    return [1. / (r[0] + 1) if r.size else 0. for r in rs]


def mean_reciprocal_rank(rs):  # iterator of relevance scores in rank order
    """ Compute mean reciprocal rank: reciprocal of the rank of the first relevant item (considering the first element
    being of 'rank 1'). Relevance is binary (nonzero is relevant).

    Args:
        rs: Iterator of relevance scores (list or numpy ndarrays) in rank order (first element is the first item)
    Returns:
        Mean reciprocal rank.
    """
    # Compute the mean of reciprocal ranks
    return np.mean(reciprocal_rank(rs))


def max_reciprocal_rank(rs):  # iterator of relevance scores in rank order
    """ Compute the maximum reciprocal rank and the index of the query it resulted from: reciprocal of the rank of the
    first relevant item (considering the first element being of 'rank 1'). Relevance is binary (nonzero is relevant).

    Args:
        rs: Iterator of relevance scores (list or numpy ndarrays) in rank order (first element is the first item)
    Returns:
        Max reciprocal rank and query index.
    """
    rr = reciprocal_rank(rs)
    return np.max(rr), np.argmax(rr)


def min_reciprocal_rank(rs):  # iterator of relevance scores in rank order
    """ Compute the minimum reciprocal rank and the index of the query it resulted from: reciprocal of the rank of the
    first relevant item (considering the first element being of 'rank 1'). Relevance is binary (nonzero is relevant).

    Args:
        rs: Iterator of relevance scores (list or numpy ndarrays) in rank order (first element is the first item)
    Returns:
        Min reciprocal rank and query index.
    """
    rr = reciprocal_rank(rs)
    return np.min(rr), np.argmin(rr)


def precision_at_k(r,  # relevance scores (list or numpy) in rank order (first element is the first item)
                   k):  # k
    """ Compute precision up to the k-th prediction. Relevance is binary (nonzero is relevant).

    Args:
        r: Relevance scores (list or numpy) in rank order (first element is the first item)
        k: k
    Returns:
        Precision up to the k-th prediction
    Raises:
        ValueError: len(r) must be >= k.
    """
    # k must be greater than 0
    assert k >= 1
    # binarize relevance scores (if one value is different from 0 set it to 1) taking only the first k values
    r = np.asarray(r)[:k] != 0
    # if the size of r is not k -> error
    if r.size != k:
        raise ValueError('Relevance score length < k')
    # return the mean of r values
    return np.mean(r)


def average_precision(r):  # relevance scores (list or numpy) in rank order (first element is the first item)
    """ Compute average precision (area under PR curve). Relevance is binary (nonzero is relevant).

    Args:
        r: Relevance scores (list or numpy) in rank order (first element is the first item)
    Returns:
        Average precision.
    """
    # binarize relevance scores (if one value is different from 0 set it to 1)
    r = np.asarray(r) != 0
    # compute ranking precisions-at-k score for all 'k's where r has a 1
    out = [precision_at_k(r, k + 1) for k in range(r.size) if r[k]]
    # if 'out' is an empty list (meaning there were no scores with value 1 in the ranking), return 0 as the AP score
    if not out:
        return 0.
    # return Average Precision (AP) computing the mean of the previously computed precisions-at-k
    return np.mean(out)


def mean_average_precision(rs):  # iterator of relevance scores in rank order
    """ Compute mean average precision. Relevance is binary (nonzero is relevant).

    Args:
        rs: Iterator of relevance scores (list or numpy) in rank order (first element is the first item)
    Returns:
        Mean average precision.
    """
    # for each numpy array in the iterator 'rs', compute the average precision (AP); then compute mean of those APs.
    return np.mean([average_precision(r) for r in rs])


def max_average_precision(rs):  # iterator of relevance scores in rank order
    """ Compute the maximum average precision and the index of the query it resulted from. Relevance is binary
    (nonzero is relevant).

    Args:
        rs: Iterator of relevance scores (list or numpy) in rank order (first element is the first item)
    Returns:
        Max average precision and query index.
    """
    # for each numpy array in the iterator 'rs', compute the average precision (AP);
    # then return the maximum AP and the query index.
    ap = [average_precision(r) for r in rs]
    return np.max(ap), np.argmax(ap)


def min_average_precision(rs):  # iterator of relevance scores in rank order
    """ Compute the minimum average precision and the index of the query it resulted from. Relevance is binary
    (nonzero is relevant).

    Args:
        rs: Iterator of relevance scores (list or numpy) in rank order (first element is the first item)
    Returns:
        Min average precision and query index.
    """
    # for each numpy array in the iterator 'rs', compute the average precision (AP);
    # then return the minimum AP and the query index.
    ap = [average_precision(r) for r in rs]
    return np.min(ap), np.argmin(ap)
