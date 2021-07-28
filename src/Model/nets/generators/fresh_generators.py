from multiprocessing import cpu_count  # used to get the number of CPUs in the system

import torch
from torch.utils import data  # we need it for the Dataloader which is at the heart of PyTorch data loading utility
from torch.utils.data import random_split
from sklearn.model_selection import train_test_split

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
                 shuffle=False):  # set to True to have the data reshuffled at every epoch
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

        if type(splits) is not list or (len(splits) != 1 and len(splits) != 3):
            raise ValueError("'splits' must be a list of 1 or 3 integers or None, got {}".format(splits))

        # check passed-in value for shuffle; it has to be either True or False
        if not ((shuffle is True) or (shuffle is False)):
            raise ValueError("'shuffle' should be either True or False, got {}".format(shuffle))

        # set up the parameters of the Dataloader
        params = {'batch_size': batch_size,
                  'shuffle': shuffle,
                  'num_workers': num_workers}

        if len(splits) == 3:
            splits_sum = sum(splits)
            for i in range(len(splits)):
                splits[i] = splits[i] / float(splits_sum)

            S, X, y = ds.get_as_tensors()

            S_train, S_valid_test, X_train, X_valid_test, y_train, y_valid_test = train_test_split(
                S, X, y, test_size=splits[1] + splits[2], stratify=y)

            S_valid, S_test, X_valid, X_test, y_valid, y_test = train_test_split(
                S_valid_test, X_valid_test, y_valid_test, test_size=splits[2], stratify=y_valid_test)

            # create Dataloaders for the previously created subsets with the specified parameters
            train_generator = data.DataLoader(data.TensorDataset(S_train, X_train, y_train), **params)
            valid_generator = data.DataLoader(data.TensorDataset(S_valid, X_valid, y_valid), **params)
            test_generator = data.DataLoader(data.TensorDataset(S_test, X_test, y_test), **params)

            self.generator = (train_generator, valid_generator, test_generator)

        else:
            # create Dataloader for the previously created dataset (ds) with the just specified parameters
            self.generator = data.DataLoader(ds, **params)

    def __call__(self):
        """ Generator-factory call method.

        Returns:
            Generator.
        """
        return self.generator


def get_generator(ds_root,  # path of the directory where to find the fresh dataset (containing .dat files)
                  splits=None,
                  batch_size=8192,  # how many samples per batch to load
                  num_workers=None,  # how many subprocesses to use for data loading by the Dataloader
                  return_shas=False,  # whether to return the sha256 of the data points or not
                  shuffle=None):  # set to True to have the data reshuffled at every epoch

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

    # return the Generator (a.k.a. Dataloader)
    return GeneratorFactory(ds_root=ds_root,
                            splits=splits,
                            batch_size=batch_size,
                            num_workers=num_workers,
                            return_shas=return_shas,
                            shuffle=shuffle)()
