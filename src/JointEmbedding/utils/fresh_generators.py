from multiprocessing import cpu_count  # Used to get the number of CPUs in the system

from torch.utils import data  # We need it for the Dataloader which is at the heart of PyTorch data loading utility

from .fresh_dataset import Dataset

# set max_workers to be equal to the current system cpu_count
max_workers = cpu_count()


class GeneratorFactory(object):

    def __init__(self,
                 ds_root,  # path of the directory where to find the fresh dataset (containing .dat files)
                 batch_size=None,  # how many samples per batch to load
                 num_workers=max_workers,  # how many subprocesses to use for data loading by the Dataloader
                 return_shas=False,  # whether to return the sha256 of the data points or not
                 shuffle=False):  # set to True to have the data reshuffled at every epoch

        # define Dataset object pointing to the fresh dataset
        ds = Dataset(ds_root=ds_root,
                     return_shas=return_shas)

        # if the batch size was not defined (it was None) then set it to a default value of 1024
        if batch_size is None:
            batch_size = 1024

        # set up the parameters of the Dataloader
        params = {'batch_size': batch_size,
                  'shuffle': shuffle,
                  'num_workers': num_workers}

        # create Dataloader for the previously created dataset (ds) with the just specified parameters
        self.generator = data.DataLoader(ds, **params)

    def __call__(self):
        return self.generator


def get_generator(ds_root,  # path of the directory where to find the fresh dataset (containing .dat files)
                  batch_size=8192,  # how many samples per batch to load
                  num_workers=None,  # how many subprocesses to use for data loading by the Dataloader
                  return_shas=False,  # whether to return the sha256 of the data points or not
                  shuffle=None):  # set to True to have the data reshuffled at every epoch

    # if num_workers was not defined (it is None) then set it to the maximum number of workers previously defined as
    # the current system cpu_count
    if num_workers is None:
        num_workers = max_workers

    # return the Generator (a.k.a. Dataloader)
    return GeneratorFactory(ds_root=ds_root,
                            batch_size=batch_size,
                            num_workers=num_workers,
                            return_shas=return_shas,
                            shuffle=shuffle)()
