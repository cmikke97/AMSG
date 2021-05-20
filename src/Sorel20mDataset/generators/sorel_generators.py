import os  # Provides a portable way of using operating system dependent functionality
from multiprocessing import cpu_count  # Used to get the number of CPUs in the system

from torch.utils import data  # We need it for the Dataloader which is at the heart of PyTorch data loading utility

from .sorel_dataset import Dataset  # import Dataset.py

# set max_workers to be equal to the current system cpu_count
max_workers = cpu_count()


class GeneratorFactory(object):
    """ Generator factory class. """

    def __init__(self,
                 ds_root,  # dataset root directory (where to find meta.db file)
                 batch_size=None,  # how many samples per batch to load
                 mode='train',  # mode of use of the dataset object (may be 'train', 'validation' or 'test')
                 num_workers=max_workers,  # how many subprocesses to use for data loading by the Dataloader
                 n_samples=-1,  # maximum number of data points to consider (-1 if you want to consider them all)
                 use_malicious_labels=False,  # whether to return the malicious label for the data points or not
                 use_count_labels=False,  # whether to return the counts for the data points or not
                 use_tag_labels=False,  # whether to return the tags for the data points or not
                 return_shas=False,  # whether to return the sha256 of the data points or not
                 features_lmdb='ember_features',  # name of the file containing the ember_features for the data
                 remove_missing_features='scan',
                 # whether to remove data points with missing features or not; it can be False/None/'scan'/filepath
                 # in case it is 'scan' a scan will be performed on the database in order to remove the data points
                 # with missing features
                 # in case it is a filepath then a file (in Json format) will be used to determine the data points
                 # with missing features
                 shuffle=False):  # set to True to have the data reshuffled at every epoch
        """ Initialize generator factory.

        Args:
            ds_root: dataset root directory (where to find meta.db file)
            batch_size: how many samples per batch to load
            mode: mode of use of the dataset object (may be 'train', 'validation' or 'test')
            num_workers: how many subprocesses to use for data loading by the Dataloader
            n_samples: number of samples to consider (-1 if you want to consider them all)
            use_malicious_labels: whether to return the malicious label for the data points or not
            use_count_labels: whether to return the counts for the data points or not
            use_tag_labels: whether to return the tags for the data points or not
            return_shas: whether to return the sha256 of the data points or not
            features_lmdb: name of the file containing the ember_features for the data
            remove_missing_features: whether to remove data points with missing features or not; it can be
                                     False/None/'scan'/filepath. In case it is 'scan' a scan will be performed on the
                                     database in order to remove the data points with missing features; in case it is
                                     a filepath then a file (in Json format) will be used to determine the data points
                                     with missing features
            shuffle: set to True to have the data reshuffled at every epoch
        """

        # if mode is not in one of the expected values raise an exception
        if mode not in {'train', 'validation', 'test'}:
            raise ValueError('invalid mode {}'.format(mode))

        # define Dataset object pointing to the dataset databases (meta.db and ember_features)
        ds = Dataset(metadb_path=os.path.join(ds_root, 'meta.db'),
                     # join dataset_root path with the common name for the meta_db
                     features_lmdb_path=os.path.join(ds_root, features_lmdb),
                     # join dataset_root path with the name of the file containing the ember_features
                     return_malicious=use_malicious_labels,
                     return_counts=use_count_labels,
                     return_tags=use_tag_labels,
                     return_shas=return_shas,
                     mode=mode,
                     n_samples=n_samples,
                     remove_missing_features=remove_missing_features)

        # if the batch size was not defined (it was None) then set it to a default value of 1024
        if batch_size is None:
            batch_size = 1024

        # check passed-in value for shuffle; it has to be either True or False
        if not ((shuffle is True) or (shuffle is False)):
            raise ValueError(f"'shuffle' should be either True or False, got {shuffle}")

        # set up the parameters of the Dataloader
        params = {'batch_size': batch_size,
                  'shuffle': shuffle,
                  'num_workers': num_workers}

        # create Dataloader for the previously created dataset (ds) with the just specified parameters
        self.generator = data.DataLoader(ds, **params)

    def __call__(self):
        """ Generator factory call method.

        Returns:
            Generator.
        """
        return self.generator


def get_generator(ds_root,  # dataset root directory (where to find meta.db file)
                  batch_size=8192,  # how many samples per batch to load
                  mode='train',  # mode of use of the dataset object (may be 'train', 'validation' or 'test')
                  num_workers=None,  # how many subprocesses to use for data loading by the Dataloader
                  n_samples=-1,  # maximum number of data points to consider (-1 if you want to consider them all)
                  use_malicious_labels=True,  # whether to return the malicious label for the data points or not
                  use_count_labels=True,  # whether to return the counts for the data points or not
                  use_tag_labels=True,  # whether to return the tags for the data points or not
                  return_shas=False,  # whether to return the sha256 of the data points or not
                  features_lmdb='ember_features',  # name of the file containing the ember_features for the data
                  remove_missing_features='scan',
                  # whether to remove data points with missing features or not; it can be False/None/'scan'/filepath
                  # in case it is 'scan' a scan will be performed on the database in order to remove the data points
                  # with missing features
                  # in case it is a filepath then a file (in Json format) will be used to determine the data points
                  # with missing features
                  shuffle=False):  # set to True to have the data reshuffled at every epoch
    """ Initialize generator factory.

    Args:
        ds_root: dataset root directory (where to find meta.db file)
        batch_size: how many samples per batch to load
        mode: mode of use of the dataset object (may be 'train', 'validation' or 'test')
        num_workers: how many subprocesses to use for data loading by the Dataloader
        n_samples: number of samples to consider (-1 if you want to consider them all)
        use_malicious_labels: whether to return the malicious label for the data points or not
        use_count_labels: whether to return the counts for the data points or not
        use_tag_labels: whether to return the tags for the data points or not
        return_shas: whether to return the sha256 of the data points or not
        features_lmdb: name of the file containing the ember_features for the data
        remove_missing_features: whether to remove data points with missing features or not; it can be
                                 False/None/'scan'/filepath. In case it is 'scan' a scan will be performed on the
                                 database in order to remove the data points with missing features; in case it is
                                 a filepath then a file (in Json format) will be used to determine the data points
                                 with missing features
        shuffle: set to True to have the data reshuffled at every epoch
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
                            features_lmdb=features_lmdb,
                            remove_missing_features=remove_missing_features,
                            shuffle=shuffle)()
