from multiprocessing import cpu_count  # used to get the number of CPUs in the system

import torch
from torch.utils import data  # we need it for the Dataloader which is at the heart of PyTorch data loading utility
from torch.utils.data import random_split

from .fresh_dataset import Dataset

# set max_workers to be equal to the current system cpu_count
max_workers = cpu_count()

DATA_SPLIT_SEED = 42


class GeneratorFactory(object):
    """ Generator factory class. """

    def __init__(self,
                 ds_root,  # path of the directory where to find the fresh dataset (containing .dat files)
                 splits=None,
                 batch_size=None,  # how many samples per batch to load
                 num_workers=max_workers,  # how many subprocesses to use for data loading by the Dataloader
                 return_shas=False,  # whether to return the sha256 of the data points or not
                 shuffle=False,  # set to True to have the data reshuffled at every epoch
                 data_split_seed=DATA_SPLIT_SEED):
        """ Initialize generator factory.

        Args:
            ds_root: Path of the directory where to find the fresh dataset (containing .dat files)
            batch_size: How many samples per batch to load
            num_workers: How many subprocesses to use for data loading by the Dataloader
            return_shas: Whether to return the sha256 of the data points or not
            shuffle: Set to True to have the data reshuffled at every epoch
        """

        # define Dataset object pointing to the fresh dataset
        ds = Dataset(ds_root=ds_root,
                     return_shas=return_shas)

        # if the batch size was not defined (it was None) then set it to a default value of 1024
        if batch_size is None:
            batch_size = 1024

        if splits is None:
            splits = [1]

        if type(splits) is not list:
            raise ValueError("'splits' must be a list of integers, got {}".format(splits))

        splits_sum = sum(splits)
        for i in range(len(splits)):
            splits[i] = (splits[i] * len(ds)) // splits_sum

        # check passed-in value for shuffle; it has to be either True or False
        if not ((shuffle is True) or (shuffle is False)):
            raise ValueError("'shuffle' should be either True or False, got {}".format(shuffle))

        # set up the parameters of the Dataloader
        params = {'batch_size': batch_size,
                  'shuffle': shuffle,
                  'num_workers': num_workers}

        ds_splits = random_split(ds, splits, generator=torch.Generator().manual_seed(data_split_seed))

        # create Dataloader for the previously created dataset (ds) with the just specified parameters
        self.generators = (data.DataLoader(subset, **params) for subset in ds_splits)

    def __call__(self):
        """ Generator-factory call method.

        Returns:
            Generator.
        """
        return self.generators


def get_generator(ds_root,  # path of the directory where to find the fresh dataset (containing .dat files)
                  splits=None,
                  batch_size=8192,  # how many samples per batch to load
                  num_workers=None,  # how many subprocesses to use for data loading by the Dataloader
                  return_shas=False,  # whether to return the sha256 of the data points or not
                  shuffle=None,  # set to True to have the data reshuffled at every epoch
                  data_split_seed=None):  # set to True to have the data reshuffled at every epoch
    """ Get generator based on the provided arguments.

    Args:
        ds_root: Path of the directory where to find the fresh dataset (containing .dat files)
        batch_size: How many samples per batch to load
        num_workers: How many subprocesses to use for data loading by the Dataloader (if None -> set to current
                     system cpu count)
        return_shas: Whether to return the sha256 of the data points or not
        shuffle: Set to True to have the data reshuffled at every epoch
    """

    # if num_workers was not defined (it is None) then set it to the maximum number of workers previously defined as
    # the current system cpu_count
    if num_workers is None:
        num_workers = max_workers

    if splits is None:
        splits = [1]

    if data_split_seed is None:
        data_split_seed = DATA_SPLIT_SEED

    # return the Generator (a.k.a. Dataloader)
    return GeneratorFactory(ds_root=ds_root,
                            splits=splits,
                            batch_size=batch_size,
                            num_workers=num_workers,
                            return_shas=return_shas,
                            shuffle=shuffle,
                            data_split_seed=data_split_seed)()
