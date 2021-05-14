from multiprocessing import cpu_count  # Used to get the number of CPUs in the system

from torch.utils import data  # We need it for the Dataloader which is at the heart of PyTorch data loading utility

from .dataset import Dataset

# set max_workers to be equal to the current system cpu_count
max_workers = cpu_count()


class GeneratorFactory(object):

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

        # if mode is not in one of the expected values raise an exception
        if mode not in {'train', 'validation', 'test'}:
            raise ValueError('invalid mode {}'.format(mode))

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
