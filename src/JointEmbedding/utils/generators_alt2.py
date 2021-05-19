import multiprocessing.pool
from multiprocessing import cpu_count  # Used to get the number of CPUs in the system

import torch

from .dataset_alt import Dataset

# set max_workers to be equal to the current system cpu_count
max_workers = cpu_count()


def get_batch(tensors,
              batch_size,
              i,
              return_malicious=False,
              return_counts=False,
              return_tags=False):
    batch = [t[i:i + batch_size] for t in tensors]
    batch_y = batch.pop()
    labels = {}

    if return_malicious:
        # get malware label for this sample through the index
        labels['malware'] = batch_y[:, 0]

    if return_counts:
        # get count for this sample through the index
        labels['count'] = batch_y[:, 1]

    if return_tags:
        # get tags list for this sample through the index
        labels['tags'] = batch_y[:, 2:]

    return *batch, labels


class FastTensorDataLoader:
    """
    A DataLoader-like object for a set of tensors that can be much faster than
    TensorDataset + DataLoader because dataloader grabs individual indices of
    the dataset and calls cat (slow).
    """

    def __init__(self,
                 *tensors,
                 batch_size=32,
                 shuffle=False,
                 num_workers=None,
                 use_malicious_labels=False,
                 use_count_labels=False,
                 use_tag_labels=False):
        """
        Initialize a FastTensorDataLoader.

        :param *tensors: tensors to store. Must have the same length @ dim 0.
        :param batch_size: batch size to load.
        :param shuffle: if True, shuffle the data *in-place* whenever an
            iterator is created out of this object.

        :returns: A FastTensorDataLoader.
        """
        if num_workers is None:
            self.num_workers = 1
        else:
            self.num_workers = num_workers
            self.async_results = []
            self.pool = multiprocessing.Pool()

        assert all(t.shape[0] == tensors[0].shape[0] for t in tensors)
        self.tensors = tensors

        self.dataset_len = self.tensors[0].shape[0]
        self.batch_size = batch_size
        self.shuffle = shuffle

        self.use_malicious_labels = use_malicious_labels
        self.use_count_labels = use_count_labels
        self.use_tag_labels = use_tag_labels

        # Calculate # batches
        n_batches, remainder = divmod(self.dataset_len, self.batch_size)
        if remainder > 0:
            n_batches += 1
        self.n_batches = n_batches

    def __iter__(self):
        if self.shuffle:
            r = torch.randperm(self.dataset_len)
            self.tensors = [t[r] for t in self.tensors]
        self.i = 0
        return self

    def __next__(self):
        if self.i >= self.dataset_len and (self.num_workers == 1 or len(self.async_results) == 0):
            if self.num_workers > 1:
                self.pool.close()
                self.pool.terminate()
            raise StopIteration

        if self.num_workers == 1:
            batch = get_batch(tensors=self.tensors,
                              batch_size=self.batch_size,
                              i=self.i,
                              return_malicious=self.use_malicious_labels,
                              return_counts=self.use_count_labels,
                              return_tags=self.use_tag_labels)
            self.i += self.batch_size
            return batch
        else:
            current_num_results = len(self.async_results)
            if self.i < self.dataset_len and current_num_results < self.num_workers:
                arguments = {
                    'tensors': self.tensors,
                    'batch_size': self.batch_size,
                    'i': self.i,
                    'return_malicious': self.use_malicious_labels,
                    'return_counts': self.use_count_labels,
                    'return_tags': self.use_tag_labels
                }
                self.async_results.append(self.pool.apply_async(get_batch, arguments))
                self.i += self.batch_size

            current_result = self.async_results.pop(0)
            return current_result.get()

    def __len__(self):
        return self.n_batches


class GeneratorFactory(object):
    """ Generator factory class """

    def __init__(self,
                 ds_root,  # path of the directory where to find the pre-processed dataset (containing .dat files)
                 batch_size=None,  # how many samples per batch to load
                 mode='train',  # mode of use of the dataset object (may be 'train', 'validation' or 'test')
                 num_workers=max_workers,  # how many subprocesses to use for data loading by the Dataloader
                 n_samples=None,  # number of samples to consider (used just to access the right pre-processed files)
                 use_malicious_labels=False,  # whether to return the malicious label for the data points or not
                 use_count_labels=False,  # whether to return the counts for the data points or not
                 use_tag_labels=False,  # whether to return the tags for the data points or not
                 return_shas=False,  # whether to return the sha256 of the data points or not
                 shuffle=None):  # set to True to have the data reshuffled at every epoch
        """ Initialize generator factory.

        Args:
            ds_root: Path of the directory where to find the pre-processed dataset (containing .dat files)
            batch_size: How many samples per batch to load
            mode: Mode of use of the dataset object (may be 'train', 'validation' or 'test')
            num_workers: How many subprocesses to use for data loading by the Dataloader
            n_samples: Number of samples to consider (used just to access the right pre-processed files)
            use_malicious_labels: Whether to return the malicious label for the data points or not
            use_count_labels: Whether to return the counts for the data points or not
            use_tag_labels: Whether to return the tags for the data points or not
            return_shas: Whether to return the sha256 of the data points or not
            shuffle: Set to True to have the data reshuffled at every epoch
        """

        # if mode is not in one of the expected values raise an exception
        if mode not in {'train', 'validation', 'test'}:
            raise ValueError('invalid mode {}'.format(mode))

        if not use_malicious_labels and not use_count_labels and not use_tag_labels:
            raise ValueError('At least one label must be used.')

        # define Dataset object pointing to the pre-precessed dataset
        ds = Dataset(ds_root=ds_root,
                     mode=mode,
                     n_samples=n_samples,
                     return_shas=return_shas)

        # if the batch size was not defined (it was None) then set it to a default value of 1024
        if batch_size is None:
            batch_size = 1024

        # check passed-in value for shuffle; if it is not None it has to be either True or False
        if shuffle is not None:
            if not ((shuffle is True) or (shuffle is False)):
                raise ValueError(f"'shuffle' should be either True or False, got {shuffle}")
        else:
            # if it is None then if mode of use is 'train' then set shuffle to True, otherwise to false
            if mode == 'train':
                shuffle = True
            else:
                shuffle = False

        # create Dataloader for the previously created dataset (ds) with the just specified parameters
        self.generator = FastTensorDataLoader(*ds.get_as_tensors(),
                                              batch_size=batch_size,
                                              shuffle=shuffle,
                                              num_workers=num_workers,
                                              use_malicious_labels=use_malicious_labels,
                                              use_count_labels=use_count_labels,
                                              use_tag_labels=use_tag_labels)

    def __call__(self):
        """ Generator factory call method.

        Returns:
            Generator
        """
        return self.generator


def get_generator(ds_root,  # path of the directory where to find the pre-processed dataset (containing .dat files)
                  batch_size=8192,  # how many samples per batch to load
                  mode='train',  # mode of use of the dataset object (may be 'train', 'validation' or 'test')
                  num_workers=None,  # how many subprocesses to use for data loading by the Dataloader
                  n_samples=None,  # number of samples to consider (used just to access the right pre-processed files)
                  use_malicious_labels=True,  # whether to return the malicious label for the data points or not
                  use_count_labels=True,  # whether to return the counts for the data points or not
                  use_tag_labels=True,  # whether to return the tags for the data points or not
                  return_shas=False,  # whether to return the sha256 of the data points or not
                  shuffle=None):  # set to True to have the data reshuffled at every epoch
    """ Get generator based on the provided arguments.

    Args:
        ds_root: Path of the directory where to find the pre-processed dataset (containing .dat files)
        batch_size: How many samples per batch to load
        mode: Mode of use of the dataset object (may be 'train', 'validation' or 'test')
        num_workers: How many subprocesses to use for data loading by the Dataloader
        n_samples: Number of samples to consider (used just to access the right pre-processed files)
        use_malicious_labels: Whether to return the malicious label for the data points or not
        use_count_labels: Whether to return the counts for the data points or not
        use_tag_labels: Whether to return the tags for the data points or not
        return_shas: Whether to return the sha256 of the data points or not
        shuffle: Set to True to have the data reshuffled at every epoch
    """

    # if num_workers was not defined (it is None) then set it to the maximum number of workers previously defined as
    # the current system cpu_count
    if num_workers is None:
        num_workers = max_workers

    # return the Generator (a.k.a. Dataloader)
    return GeneratorFactory(ds_root=ds_root,
                            batch_size=batch_size,
                            mode=mode,
                            num_workers=num_workers,
                            n_samples=n_samples,
                            use_malicious_labels=use_malicious_labels,
                            use_count_labels=use_count_labels,
                            use_tag_labels=use_tag_labels,
                            return_shas=return_shas,
                            shuffle=shuffle)()
