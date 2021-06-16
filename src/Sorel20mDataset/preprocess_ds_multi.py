import configparser  # implements a basic configuration language for Python programs
import os  # provides a portable way of using operating system dependent functionality
import re  # provides regular expression matching operations
import shutil  # used to recursively copy an entire directory tree rooted at src to a directory named dst
import sys  # system-specific parameters and functions
import tempfile  # used to create temporary files and directories

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import torch  # tensor library like NumPy, with strong GPU support
from tqdm import tqdm  # instantly makes loops show a smart progress meter
from logzero import logger  # robust and effective logging for Python

from generators.sorel_dataset import Dataset
from generators.sorel_generators import get_generator
from utils.preproc_utils import steps


# get config file path
generators_dir = os.path.dirname(os.path.abspath(__file__))
sorel20mDataset_dir = os.path.dirname(generators_dir)
src_dir = os.path.dirname(sorel20mDataset_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# instantiate key-n_samples dict
total_n_samples = {'train': config['sorel20mDataset']['total_training_samples'],
                   'validation': config['sorel20mDataset']['total_validation_samples'],
                   'test': config['sorel20mDataset']['total_test_samples']}


@baker.command
def preprocess_ds_multi(ds_path,  # the path to the directory containing the meta.db file
                        destination_dir,  # the directory where to save the pre-processed dataset files
                        training_n_samples=0,  # max number of training data samples to use (if 0 -> takes all)
                        validation_n_samples=0,  # max number of validation data samples to use (if 0 -> takes all)
                        test_n_samples=0,  # max number of test data samples to use (if 0 -> takes all)
                        batch_size=8192,  # how many samples per batch to load
                        n_batches=10,  # number of batches to save in one single file (if 0 -> takes all)
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
    """ Pre-process Sorel20M dataset in multiple small files.

    Args:
        ds_path: The path to the directory containing the meta.db file
        destination_dir: The directory where to save the pre-processed dataset files
        training_n_samples: Max number of training data samples to use (if 0 -> takes all)
        validation_n_samples: Max number of validation data samples to use (if 0 -> takes all)
        test_n_samples: Max number of test data samples to use (if 0 -> takes all)
        batch_size: How many samples per batch to load
        n_batches: Number of batches to save in one single file (if 0 -> takes all). (default: 10)
        workers: How many worker processes should the dataloader use (if None use multiprocessing.cpu_count())
        remove_missing_features: Whether to remove data points with missing features or not; it can be
                                 False/None/'scan'/filepath. In case it is 'scan' a scan will be performed on the
                                 database in order to remove the data points with missing features; in case it is
                                 a filepath then a file (in Json format) will be used to determine the data points
                                 with missing features
        binarize_tag_labels: Whether to binarize or not the tag values
    """

    # instantiate key-n_samples dict
    n_samples_dict = {'train': training_n_samples if training_n_samples > 0 else total_n_samples['train'],
                      'validation': validation_n_samples if validation_n_samples > 0 else total_n_samples['validation'],
                      'test': test_n_samples if test_n_samples > 0 else total_n_samples['test']}

    # start mlflow run
    with mlflow.start_run():

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

        # create temporary directory
        with tempfile.TemporaryDirectory() as tempdir:

            # for each key (train, validation and test)
            for key in dataloaders.keys():
                logger.info('Now pre-processing {} dataset...'.format(key))

                # set curr_n_batches to be equal to the provided 'n_batches' if n_batches is greater than 0,
                # otherwise set it to the total amount of batches in the current dataloader
                curr_n_batches = n_batches if n_batches > 0 else len(dataloaders[key])

                # initialize starting index
                start = 0
                # initialize current batch index
                curr_b = -1
                # initialize number of samples
                N = 0

                # for each batch of data
                for i, (shas, features, labels) in enumerate(tqdm(dataloaders[key])):
                    # get current batch size from shas vector
                    current_batch_size = len(shas)

                    # every 'curr_n_batches' batches
                    if i // curr_n_batches != curr_b:
                        # reset starting index and current number of samples 'N'
                        start = 0
                        N = 0

                        # set current batch index
                        curr_b = i // curr_n_batches

                        # generate X (features vector), y (labels vector) and S (shas) file names
                        X_filename = "X_{}_{}_part_{}.dat".format(key, n_samples_dict[key], curr_b)
                        y_filename = "y_{}_{}_part_{}.dat".format(key, n_samples_dict[key], curr_b)
                        S_filename = 'S_{}_{}_part_{}.dat'.format(key, n_samples_dict[key], curr_b)

                        # generate X (features vector), y (labels vector) and S (shas) paths
                        X_path = os.path.join(tempdir, X_filename)
                        y_path = os.path.join(tempdir, y_filename)
                        S_path = os.path.join(tempdir, S_filename)

                        # Create space on disk to write features, labels and shas to
                        X = np.memmap(X_path, dtype=np.float32, mode="w+", shape=(current_batch_size, features_dim))
                        y = np.memmap(y_path, dtype=np.float32, mode="w+", shape=(current_batch_size, labels_dim))
                        S = np.memmap(S_path, dtype=np.dtype('U64'), mode="w+", shape=(current_batch_size,))
                        # delete X, y and S vectors -> this will flush the memmap instances writing the changes to files
                        del X, y, S

                    # compute ending index and current number of samples
                    end = start + current_batch_size
                    N += current_batch_size

                    # open X memory map in Read+ mode (extending it with the new N dimension)
                    S = np.memmap(S_path, dtype=np.dtype('U64'), mode="r+", shape=(N,))
                    # save current feature vectors
                    S[start:end] = shas

                    # open y memory map in Read+ mode (extending it with the new N dimension)
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

                    # open X memory map in Read+ mode (extending it with the new N dimension)
                    X = np.memmap(X_path, dtype=np.float32, mode="r+", shape=(N, features_dim))
                    # save current feature vectors
                    X[start:end] = features

                    # update starting index
                    start = end

                    # if this was the last of the 'n_batches' for the current file or there is no more data
                    if (i + 1) // curr_n_batches != curr_b or (i + 1) == len(dataloaders[key]):
                        # delete X, y and S vectors -> this will flush the memmap instances writing the changes to files
                        del X, y, S
                        # move completed files to destination directory (in my case it will be on google drive)
                        shutil.move(X_path, os.path.join(destination_dir, X_filename))
                        shutil.move(y_path, os.path.join(destination_dir, y_filename))
                        shutil.move(S_path, os.path.join(destination_dir, S_filename))


@baker.command
def combine_ds_files(ds_path,  # path to the directory containing the pre-processed dataset (.dat) part files
                     training_n_samples=0,  # max number of training data samples to use (if 0 -> takes all)
                     validation_n_samples=0,  # max number of validation data samples to use (if 0 -> takes all)
                     test_n_samples=0):  # max number of test data samples to use (if 0 -> takes all)
    """ Combine the pre-processed part files (.dat) into the corresponding single dataset files.

    Args:
        ds_path: Path to the directory containing the pre-processed dataset (.dat) part files
        training_n_samples: Max number of training data samples to use (if 0 -> takes all) (default: -1)
        validation_n_samples: Max number of validation data samples to use (if 0 -> takes all) (default: -1)
        test_n_samples: Max number of test data samples to use (if 0 -> takes all) (default: -1)
    """

    # instantiate key-n_samples dict
    n_samples_dict = {'train': training_n_samples if training_n_samples > 0 else total_n_samples['train'],
                      'validation': validation_n_samples if validation_n_samples > 0 else total_n_samples['validation'],
                      'test': test_n_samples if test_n_samples > 0 else total_n_samples['test']}

    # file types: S (shas), X (feature vectors) and y (labels)
    ftypes = ['S', 'X', 'y']

    # start mlflow run
    with mlflow.start_run():
        # get the names of all files inside the ds_path directory
        all_file_names = [f for f in os.listdir(ds_path) if os.path.isfile(os.path.join(ds_path, f))]

        # set features dimension
        features_dim = 2381

        # set labels dimension to 1 (malware) + 1 (count) + n_tags (tags)
        labels_dim = 1 + 1 + len(Dataset.tags)

        # for each key (train, validation and test)
        for step in steps:
            # instantiate current_step_files and indexes dictionaries
            current_step_files = {}
            indexes = {}

            logger.info('Now combining {} dataset files...'.format(step))

            # for each file type
            for ftype in ftypes:

                # instantiate an entry for the current file type inside the current_step_files dictionary
                current_step_files[ftype] = {}
                # for each file name in the ds_path directory
                for f in all_file_names:
                    # match a regex expression
                    m = re.match("{}_{}_{}_part_(\d+).dat".format(ftype, step, n_samples_dict[step]), f)
                    if m:  # if the file matched then add it to current_step_files for the current type and file index
                        current_step_files[ftype][m.group(1)] = f

                # get (and sort) all file indexes for the current type
                indexes[ftype] = sorted([int(i) for i in current_step_files[ftype].keys()])
                logger.info('Found {} part files. Got parts [{}].'
                            .format('{}_{}_{}'.format(ftype, step, n_samples_dict[step]),
                                    ', '.join([str(i) for i in indexes[ftype]])))
                # if no files were found for the current file type, or some files were missing, log error and exit
                if len(indexes[ftype]) == 0 or \
                        (int(max(indexes[ftype])) - int(min(indexes[ftype])) + 1 != len(indexes[ftype])):
                    logger.error('Some {} part files are missing. Got parts [{}].'
                                 .format('{}_{}_{}'.format(ftype, step, n_samples_dict[step]),
                                         ', '.join([str(i) for i in indexes[ftype]])))
                    sys.exit(1)

            # assert that the number of files found for the different file types is the same
            assert (len(indexes['S']) == len(indexes['X']) and len(indexes['S']) == len(indexes['y']))
            assert (max(indexes['S']) == max(indexes['X']) and max(indexes['S']) == max(indexes['y']))
            assert (min(indexes['S']) == min(indexes['X']) and min(indexes['S']) == min(indexes['y']))

            # create S, X and y final file names
            S_path = os.path.join(ds_path, "S_{}_{}.dat".format(step, n_samples_dict[step]))
            X_path = os.path.join(ds_path, "X_{}_{}.dat".format(step, n_samples_dict[step]))
            y_path = os.path.join(ds_path, "y_{}_{}.dat".format(step, n_samples_dict[step]))

            # initialize number of samples (N) and starting index
            N = 0
            start = 0

            # for each file index
            for i in tqdm(range(len(indexes['S']))):
                # create current S, X and y file names
                S_path_curr = os.path.join(ds_path, current_step_files['S'][str(i)])
                X_path_curr = os.path.join(ds_path, current_step_files['X'][str(i)])
                y_path_curr = os.path.join(ds_path, current_step_files['y'][str(i)])

                # open current S numpy memmap in read mode
                S_curr = np.memmap(S_path_curr, dtype=np.dtype('U64'), mode="r")
                # get the current number of samples from S memmap
                N_curr = S_curr.shape[0]

                # update ending index
                end = start + N_curr
                # undate number of samples
                N += N_curr

                # open current X and y numpy memmaps in read mode
                X_curr = np.memmap(X_path_curr, dtype=np.float32, mode="r", shape=(N_curr, features_dim))
                y_curr = np.memmap(y_path_curr, dtype=np.float32, mode="r", shape=(N_curr, labels_dim))

                # if this is the first iteration, open final S, X and y numpy memmaps in write+ mode
                if i == 0:
                    S = np.memmap(S_path, dtype=np.dtype('U64'), mode="w+", shape=(N,))
                    X = np.memmap(X_path, dtype=np.float32, mode="w+", shape=(N, features_dim))
                    y = np.memmap(y_path, dtype=np.float32, mode="w+", shape=(N, labels_dim))
                else:  # otherwise open them in read+ mode (extending them with the new N dimension)
                    S = np.memmap(S_path, dtype=np.dtype('U64'), mode="r+", shape=(N,))
                    X = np.memmap(X_path, dtype=np.float32, mode="r+", shape=(N, features_dim))
                    y = np.memmap(y_path, dtype=np.float32, mode="r+", shape=(N, labels_dim))

                # save the current data
                S[start:end] = S_curr
                X[start:end] = X_curr
                y[start:end] = y_curr

                # update starting index
                start = end

                # delete X, y and S vectors -> this will flush the memmap instances writing the changes to files
                del S_curr, X_curr, y_curr, S, X, y
                # remove the used part files
                os.remove(S_path_curr)
                os.remove(X_path_curr)
                os.remove(y_path_curr)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
