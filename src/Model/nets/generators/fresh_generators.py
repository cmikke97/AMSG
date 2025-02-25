# Copyright 2021, Crepaldi Michele.
#
# Developed as a thesis project at the TORSEC research group of the Polytechnic of Turin (Italy) under the supervision
# of professor Antonio Lioy and engineer Andrea Atzeni and with the support of engineer Andrea Marcelli.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

import math  # provides access to the mathematical functions defined by the C standard
from multiprocessing import cpu_count  # used to get the number of CPUs in the system

import numpy as np  # the fundamental package for scientific computing with Python
from torch.utils import data  # we need it for the Dataloader which is at the heart of PyTorch data loading utility

from .fresh_dataset import Dataset

# set max_workers to be equal to the current system cpu_count
max_workers = cpu_count()


def train_valid_test_split(*tensors,  # set of tensors to split
                           proportions,  # proportions (floats) to follow while splitting the tensors
                           n_samples_tot,  # total number of samples in the original tensors
                           n_families):  # number of families in the original tensors
    """ Split a set of already instantiated tensors (memmaps) into train, valid and test subsplits following the given
    proportions keeping balance between families.

    Args:
        *tensors: Set of tensors to split
        proportions: Proportions (floats) to follow while splitting the tensors
        n_samples_tot: Total number of samples in the original tensors
        n_families: Number of families in the original tensors
    Returns:
        List containing the created subsplits (train, valid and test) for all input tensors
    """

    # get total number of samples per family in the original tensors
    n_samples_per_family = n_samples_tot // n_families

    # compute the number of samples (per family) to get following the given proportions.
    # the samples belonging to the same family appear one after the other; once there are no more samples of one family
    # the samples of another family are present. Moreover, the samples are ordered by the time they were first seen
    # (the newest first). Therefore, the first subsplits to produce are the test ones.
    n_samples = {
        'test': math.floor(proportions[2] * n_samples_per_family),
        'valid': math.floor(proportions[1] * n_samples_per_family),
        'train': math.ceil(proportions[0] * n_samples_per_family)
    }

    # initialize inicies dict
    indices = {}
    # for each family
    for i in range(n_families):
        # if it is the first family
        if i == 0:
            # set starting position in the input tensors
            start = 0
            # for each subsplit, get the subplit name and number of samples per family to get
            for k, v in n_samples.items():
                # compute the ending position in the input tensors given the current number of samples to get
                end = start + v
                # compute the numpy array of indices for the current subplit
                indices[k] = np.arange(start, end)
                # update starting position
                start = end
        else:
            # set starting position in the input tensors depending on the current family number
            start = i * n_samples_per_family
            # for each subsplit, get the subplit name and number of samples per family to get
            for k, v in n_samples.items():
                # compute the ending position in the input tensors given the current number of samples to get
                end = start + v
                # update the numpy array of indices for the current subplit
                indices[k] = np.concatenate((indices[k], np.arange(start, end)), axis=0)
                # update starting position
                start = end

    # initialize empty result value
    rv = []

    # for each input tensor
    for t in tensors:
        # append to the return value list the subsplits of the current tensor
        rv.append(t[indices['train']])
        rv.append(t[indices['valid']])
        rv.append(t[indices['test']])

    # return splitted tensors
    return rv


class GeneratorFactory(object):
    """ Generator factory class. """

    def __init__(self,
                 ds_root,  # path of the directory where to find the fresh dataset (containing .dat files)
                 splits=None,  # list of 3 ints corresponding to the train, valid and test subsets relative proportions
                 batch_size=None,  # how many samples per batch to load
                 num_workers=max_workers,  # how many subprocesses to use for data loading by the Dataloader
                 return_shas=False,  # whether to return the sha256 of the data points or not
                 shuffle=False):  # set to True to have the data reshuffled at every epoch
        """ Initialize generator factory optionally splitting the fresh dataset into training, validation and test
        subsplits.

        Args:
            ds_root: Path of the directory where to find the fresh dataset (containing .dat files)
            splits: List of 3 ints corresponding to the train, valid and test subsets relative proportions
                    (default: None)
            batch_size: How many samples per batch to load (default: None)
            num_workers: How many subprocesses to use for data loading by the Dataloader (default: max_workers)
            return_shas: Whether to return the sha256 of the data points or not (default: False)
            shuffle: Set to True to have the data reshuffled at every epoch (default: False)
        """

        # if the batch size was not defined (it was None) then set it to a default value of 1024
        if batch_size is None:
            batch_size = 1024

        # if no splits are provided then set one single split with proportion 1
        if splits is None:
            splits = [1]

        # if splits is not as expected raise value error
        if type(splits) is not list or (len(splits) != 1 and len(splits) != 3):
            raise ValueError("'splits' must be a list of 1 or 3 integers or None, got {}".format(splits))

        if shuffle is not None:
            # check passed-in value for shuffle; it has to be either True or False
            if not ((shuffle is True) or (shuffle is False)):
                raise ValueError("'shuffle' should be either True or False, got {}".format(shuffle))
        else:
            shuffle: False

        # set up the parameters of the Dataloader
        params = {'batch_size': batch_size,
                  'shuffle': shuffle,
                  'num_workers': num_workers}

        # if the number of splits is exactly 3
        if len(splits) == 3:
            # define Dataset object pointing to the fresh dataset
            ds = Dataset.from_file(ds_root=ds_root, return_shas=True)

            # get sum of split proportions
            splits_sum = sum(splits)
            # for all split proportions
            for i in range(len(splits)):
                # set proportion to be a fraction of the total sum
                splits[i] = splits[i] / float(splits_sum)

            # get instantiated tensors from the whole fresh dataset
            S, X, y = ds.get_as_tensors()

            # split tensors into train, valid and test subsplits following the proportions defined by 'splits'
            S_train, S_valid, S_test, X_train, X_valid, X_test, y_train, y_valid, y_test = train_valid_test_split(
                S, X, y, proportions=splits, n_samples_tot=len(ds), n_families=ds.n_families)

            # create Dataloaders for the previously created subsets with the specified parameters
            train_generator = data.DataLoader(Dataset(S_train, X_train, y_train,
                                                      sig_to_label_dict=ds.sig_to_label_dict,
                                                      return_shas=return_shas), **params)
            valid_generator = data.DataLoader(Dataset(S_valid, X_valid, y_valid,
                                                      sig_to_label_dict=ds.sig_to_label_dict,
                                                      return_shas=return_shas), **params)
            test_generator = data.DataLoader(Dataset(S_test, X_test, y_test,
                                                     sig_to_label_dict=ds.sig_to_label_dict,
                                                     return_shas=return_shas), **params)

            # return created dataloaders
            self.generator = (train_generator, valid_generator, test_generator)

        else:  # otherwise, if the number of splits is 1
            # define Dataset object pointing to the fresh dataset
            ds = Dataset.from_file(ds_root=ds_root, return_shas=return_shas)

            # create Dataloader for the previously created dataset (ds) with the just specified parameters
            self.generator = data.DataLoader(ds, **params)

    def __call__(self):
        """ Generator-factory call method.

        Returns:
            Generator.
        """
        return self.generator


def get_generator(ds_root,  # path of the directory where to find the fresh dataset (containing .dat files)
                  splits=None,  # list of 3 ints corresponding to the train, valid and test subsets relative proportions
                  batch_size=8192,  # how many samples per batch to load
                  num_workers=None,  # how many subprocesses to use for data loading by the Dataloader
                  return_shas=False,  # whether to return the sha256 of the data points or not
                  shuffle=None):  # set to True to have the data reshuffled at every epoch

    """ Get generator based on the provided arguments.

    Args:
        ds_root: Path of the directory where to find the fresh dataset (containing .dat files)
        splits: List of 3 ints corresponding to the train, valid and test subsets relative proportions
                (default: None)
        batch_size: How many samples per batch to load (default: 8192)
        num_workers: How many subprocesses to use for data loading by the Dataloader (if None -> set to current
                     system cpu count) (default: None)
        return_shas: Whether to return the sha256 of the data points or not (default: False)
        shuffle: Set to True to have the data reshuffled at every epoch (default: None)
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
