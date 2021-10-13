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

from multiprocessing import cpu_count  # Used to get the number of CPUs in the system

from torch.utils import data  # We need it for the Dataloader which is at the heart of PyTorch data loading utility

from .dataset import Dataset

# set max_workers to be equal to the current system cpu_count
max_workers = cpu_count()


class GeneratorFactory(object):
    """ Generator factory class. """

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
        """ Initialize generator factory class.

        Args:
            ds_root: Path of the directory where to find the pre-processed dataset (containing .dat files)
            batch_size: How many samples per batch to load (default: None -> 1024)
            mode: Mode of use of the dataset object (may be 'train', 'validation' or 'test') (default: 'train')
            num_workers: How many subprocesses to use for data loading by the Dataloader (default: max_workers)
            n_samples: Number of samples to consider (used just to access the right pre-processed files)
                       (default: None -> all)
            use_malicious_labels: Whether to return the malicious label for the data points or not (default: False)
            use_count_labels: Whether to return the counts for the data points or not (default: False)
            use_tag_labels: Whether to return the tags for the data points or not (default: False)
            return_shas: Whether to return the sha256 of the data points or not (default: False)
            shuffle: Set to True to have the data reshuffled at every epoch (default: None -> if mode is 'train'
                     then shuffle is set to True, otherwise it is set to False)
        """

        # if mode is not in one of the expected values raise an exception
        if mode not in {'train', 'validation', 'test'}:
            raise ValueError('invalid mode {}'.format(mode))

        # check use_malicious_labels, use_count_labels and use_tag_labels, at least one has to be true
        if not use_malicious_labels and not use_count_labels and not use_tag_labels:
            raise ValueError('At least one label must be used.')

        # define Dataset object pointing to the pre-precessed dataset
        ds = Dataset(ds_root=ds_root,
                     mode=mode,
                     n_samples=n_samples,
                     return_malicious=use_malicious_labels,
                     return_counts=use_count_labels,
                     return_tags=use_tag_labels,
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

        # set up the parameters of the Dataloader
        params = {'batch_size': batch_size,
                  'shuffle': shuffle,
                  'num_workers': num_workers}

        # create Dataloader for the previously created dataset (ds) with the just specified parameters
        self.generator = data.DataLoader(ds, **params)

    def __call__(self):
        """ Generator-factory call method.

        Returns:
            Generator.
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
        batch_size: How many samples per batch to load (default: 8192)
        mode: Mode of use of the dataset object (may be 'train', 'validation' or 'test') (default: 'train')
        num_workers: How many subprocesses to use for data loading by the Dataloader (if None -> set to current
                    system cpu count) (default: None)
        n_samples: Number of samples to consider (used just to access the right pre-processed files)
                   (default: None -> all)
        use_malicious_labels: Whether to return the malicious label for the data points or not (default: False)
        use_count_labels: Whether to return the counts for the data points or not (default: False)
        use_tag_labels: Whether to return the tags for the data points or not (default: False)
        return_shas: Whether to return the sha256 of the data points or not (default: False)
        shuffle: Set to True to have the data reshuffled at every epoch (default: None -> if mode is 'train'
                     then shuffle is set to True, otherwise it is set to False)
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
