import os  # provides a portable way of using operating system dependent functionality

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import torch  # tensor library like NumPy, with strong GPU support
import tqdm  # instantly makes loops show a smart progress meter
from logzero import logger  # robust and effective logging for Python

from generators.sorel_dataset import Dataset
from generators.sorel_generators import get_generator
from utils.preproc_utils import check_files, steps


@baker.command
def preprocess_dataset(ds_path,  # the path to the directory containing the meta.db file
                       destination_dir,  # the directory where to save the pre-processed dataset files
                       training_n_samples=-1,  # max number of training data samples to use (if -1 -> takes all)
                       validation_n_samples=-1,  # max number of validation data samples to use (if -1 -> takes all)
                       test_n_samples=-1,  # max number of test data samples to use (if -1 -> takes all)
                       batch_size=8192,  # how many samples per batch to load
                       workers=None,  # how many worker processes should the dataloader use
                       # remove_missing_features:
                       # Strategy for removing missing samples, with meta.db entries but no associated features, from
                       # the data.
                       # Must be one of: 'scan', 'none', or path to a missing keys file.
                       # Setting to 'scan' (default) will check all entries in the LMDB and remove any keys that are
                       # missing -- safe but slow.
                       # Setting to 'none' will not perform a check, but may lead to a run failure if any features are
                       # missing.
                       # Setting to a path will attempt to load a json-serialized list of SHA256 values from the
                       # specified file, indicating which keys are missing and should be removed from the dataloader.
                       remove_missing_features='scan',
                       binarize_tag_labels=True):  # whether to binarize or not the tag values
    """ Pre-process Sorel20M dataset.

    Args:
        ds_path: The path to the directory containing the meta.db file
        destination_dir: The directory where to save the pre-processed dataset files
        training_n_samples: Max number of training data samples to use (if -1 -> takes all)
        validation_n_samples: Max number of validation data samples to use (if -1 -> takes all)
        test_n_samples: Max number of test data samples to use (if -1 -> takes all)
        batch_size: How many samples per batch to load
        workers: How many worker processes should the dataloader use (if None use multiprocessing.cpu_count())
        remove_missing_features: Whether to remove data points with missing features or not; it can be
                                 False/None/'scan'/filepath. In case it is 'scan' a scan will be performed on the
                                 database in order to remove the data points with missing features; in case it is
                                 a filepath then a file (in Json format) will be used to determine the data points
                                 with missing features
        binarize_tag_labels: Whether to binarize or not the tag values
    """

    ds_path = os.path.normpath(ds_path)
    destination_dir = os.path.normpath(destination_dir)
    if remove_missing_features is not None and remove_missing_features != 'scan':
        remove_missing_features = os.path.normpath(remove_missing_features)

    # instantiate key-n_samples dict
    n_samples_dict = {'train': training_n_samples,
                      'validation': validation_n_samples,
                      'test': test_n_samples}

    # start mlflow run
    with mlflow.start_run():

        # check if the dataset was already pre-processed, if yes return
        if check_files(destination_dir=destination_dir, n_samples_dict=n_samples_dict):
            logger.info("Found already pre-processed dataset..")
            return

        # instantiate the train, valid and test dataloaders
        dataloaders = {key: get_generator(ds_root=ds_path,
                                          mode=key,
                                          use_malicious_labels=True,
                                          use_count_labels=True,
                                          use_tag_labels=True,
                                          batch_size=batch_size,
                                          num_workers=workers,
                                          return_shas=True,
                                          n_samples=n_samples_dict[key],
                                          remove_missing_features=remove_missing_features) for key in steps}
        # create result directory
        os.makedirs(destination_dir, exist_ok=True)

        # set features dimension
        features_dim = 2381

        # set labels dimension to 1 (malware) + 1 (count) + n_tags (tags)
        labels_dim = 1 + 1 + len(Dataset.tags)

        # for each key (train, validation and test)
        for key in dataloaders.keys():
            logger.info('Now pre-processing {} dataset...'.format(key))

            # generate X (features vector), y (labels vector) and S (shas) file names
            X_path = os.path.join(destination_dir, "X_{}_{}.dat".format(key, n_samples_dict[key]))
            y_path = os.path.join(destination_dir, "y_{}_{}.dat".format(key, n_samples_dict[key]))
            S_path = os.path.join(destination_dir, 'S_{}_{}.dat'.format(key, n_samples_dict[key]))

            # get total number of samples in the dataset
            N = len(dataloaders[key].dataset)

            # Create space on disk to write features, labels and shas to
            X = np.memmap(X_path, dtype=np.float32, mode="w+", shape=(N, features_dim))
            y = np.memmap(y_path, dtype=np.float32, mode="w+", shape=(N, labels_dim))
            S = np.memmap(S_path, dtype=np.dtype('U64'), mode="w+", shape=(N,))
            # delete X, y and S vectors -> this will flush the memmap instance writing the changes to the files
            del X, y, S

            # initialize starting index
            start = 0

            # for each batch of data
            for shas, features, labels in tqdm.tqdm(dataloaders[key]):
                current_batch_size = len(shas)

                # compute ending index
                end = start + current_batch_size

                # open X memory map in Read+ mode
                S = np.memmap(S_path, dtype=np.dtype('U64'), mode="r+", shape=(N,))
                # save current feature vectors
                S[start:end] = shas

                # open y memory map in Read+ mode
                y = np.memmap(y_path, dtype=np.float32, mode="r+", shape=(N, labels_dim))

                # get single labels
                malware_labels = torch.unsqueeze(labels['malware'], 1)
                count_labels = torch.unsqueeze(labels['count'], 1)
                tags_labels = labels['tags']
                if binarize_tag_labels:
                    # binarize the tag labels
                    # -> if the tag is different from 0 then it is set 1, otherwise it is set to 0
                    tags_labels = torch.ne(tags_labels, 0).to(dtype=torch.float32)

                # save current labels
                y[start:end] = torch.cat((malware_labels, count_labels, tags_labels), dim=1)

                # open X memory map in Read+ mode
                X = np.memmap(X_path, dtype=np.float32, mode="r+", shape=(N, features_dim))
                # save current feature vectors
                X[start:end] = features

                # update starting index
                start += current_batch_size


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
