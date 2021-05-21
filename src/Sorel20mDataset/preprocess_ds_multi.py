import os  # Provides a portable way of using operating system dependent functionality
import re
import shutil
import sys
import tempfile

import baker  # Easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # The fundamental package for scientific computing with Python
import torch  # Tensor library like NumPy, with strong GPU support
import tqdm  # Instantly makes loops show a smart progress meter
from logzero import logger  # Robust and effective logging for Python

from generators.sorel_dataset import Dataset
from generators.sorel_generators import get_generator
from utils.preproc_utils import steps


@baker.command
def preprocess_ds_multi(ds_path,  # the path to the directory containing the meta.db file
                        destination_dir,  # the directory where to save the pre-processed dataset files
                        training_n_samples=-1,  # max number of training data samples to use (if -1 -> takes all)
                        validation_n_samples=-1,  # max number of validation data samples to use (if -1 -> takes all)
                        test_n_samples=-1,  # max number of test data samples to use (if -1 -> takes all)
                        batch_size=8192,  # how many samples per batch to load
                        n_batches=10,  # number of batches to save in one single file (if -1 -> takes all)
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
        ds_path: the path to the directory containing the meta.db file
        destination_dir: the directory where to save the pre-processed dataset files
        training_n_samples: max number of training data samples to use (if -1 -> takes all)
        validation_n_samples: max number of validation data samples to use (if -1 -> takes all)
        test_n_samples: max number of test data samples to use (if -1 -> takes all)
        batch_size: how many samples per batch to load
        n_batches: number of batches to save in one single file (if -1 -> takes all). (default: 10)
        workers: how many worker processes should the dataloader use (if None use multiprocessing.cpu_count())
        remove_missing_features: whether to remove data points with missing features or not; it can be
                                 False/None/'scan'/filepath. In case it is 'scan' a scan will be performed on the
                                 database in order to remove the data points with missing features; in case it is
                                 a filepath then a file (in Json format) will be used to determine the data points
                                 with missing features
        binarize_tag_labels: whether to binarize or not the tag values
    """

    # instantiate key-n_samples dict
    n_samples_dict = {'train': training_n_samples,
                      'validation': validation_n_samples,
                      'test': test_n_samples}

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

        with tempfile.TemporaryDirectory() as tempdir:

            # for each key (train, validation and test)
            for key in dataloaders.keys():
                logger.info('Now pre-processing {} dataset...'.format(key))

                # initialize starting index
                start = 0
                curr_b = -1
                N = 0
                for i, (shas, features, labels) in enumerate(tqdm.tqdm(dataloaders[key])):
                    current_batch_size = len(shas)

                    if i // n_batches != curr_b:
                        start = 0
                        N = current_batch_size

                        curr_b = i // n_batches

                        X_filename = "X_{}_{}_part_{}.dat".format(key, n_samples_dict[key], curr_b)
                        y_filename = "y_{}_{}_part_{}.dat".format(key, n_samples_dict[key], curr_b)
                        S_filename = 'S_{}_{}_part_{}.dat'.format(key, n_samples_dict[key], curr_b)

                        # generate X (features vector), y (labels vector) and S (shas) file names
                        X_path = os.path.join(tempdir, X_filename)
                        y_path = os.path.join(tempdir, y_filename)
                        S_path = os.path.join(tempdir, S_filename)

                        # Create space on disk to write features, labels and shas to
                        X = np.memmap(X_path, dtype=np.float32, mode="w+", shape=(N, features_dim))
                        y = np.memmap(y_path, dtype=np.float32, mode="w+", shape=(N, labels_dim))
                        S = np.memmap(S_path, dtype=np.dtype('U64'), mode="w+", shape=(N,))
                        # delete X, y and S vectors -> this will flush the memmap instance writing the changes to files
                        del X, y, S

                    # compute ending index
                    end = start + current_batch_size
                    N += current_batch_size

                    # open X memory map in Read+ mode
                    S = np.memmap(S_path, dtype=np.dtype('U64'), mode="r+", shape=(N,), order='C')
                    # save current feature vectors
                    S[start:end] = shas

                    # open y memory map in Read+ mode
                    y = np.memmap(y_path, dtype=np.float32, mode="r+", shape=(N, labels_dim), order='C')

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
                    X = np.memmap(X_path, dtype=np.float32, mode="r+", shape=(N, features_dim), order='C')
                    # save current feature vectors
                    X[start:end] = features

                    # update starting index
                    start = end

                    if (i + 1) // n_batches != curr_b:
                        del X, y, S
                        # move completed files to destination directory (in my case it will be on google drive)
                        shutil.move(X_path, os.path.join(destination_dir, X_filename))
                        shutil.move(y_path, os.path.join(destination_dir, y_filename))
                        shutil.move(S_path, os.path.join(destination_dir, S_filename))


@baker.command
def combine_ds_files(ds_path,  # the path to the directory containing the meta.db file
                     training_n_samples=-1,  # max number of training data samples to use (if -1 -> takes all)
                     validation_n_samples=-1,  # max number of validation data samples to use (if -1 -> takes all)
                     test_n_samples=-1):  # max number of test data samples to use (if -1 -> takes all)

    # instantiate key-n_samples dict
    n_samples_dict = {'train': training_n_samples,
                      'validation': validation_n_samples,
                      'test': test_n_samples}

    ftypes = ['S', 'X', 'y']

    # start mlflow run
    with mlflow.start_run():
        all_file_names = [f for f in os.listdir(ds_path) if os.path.isfile(os.path.join(ds_path, f))]

        # set features dimension
        features_dim = 2381

        # set labels dimension to 1 (malware) + 1 (count) + n_tags (tags)
        labels_dim = 1 + 1 + len(Dataset.tags)

        # for each key (train, validation and test)
        for step in steps:
            current_step_files = {}
            indexes = {}
            logger.info('Now combining {} dataset files...'.format(step))

            for ftype in ftypes:

                current_step_files[ftype] = {}
                for f in all_file_names:
                    m = re.match("{}_{}_{}_part_(\d+).dat".format(ftype, step, n_samples_dict[step]), f)
                    if m:
                        current_step_files[ftype][m.group(1)] = f

                indexes[ftype] = [i for i in sorted(current_step_files[ftype].keys())]
                if len(indexes[ftype]) == 0 or \
                        (int(max(indexes[ftype])) - int(min(indexes[ftype])) + 1 != len(indexes[ftype])):
                    separator = ', '
                    logger.error('Some {} part files are missing. Got parts [{}].'
                                 .format('{}_{}_{}'.format(ftype, step, n_samples_dict[step]),
                                         separator.join(indexes[ftype])))
                    sys.exit(1)

            assert (len(indexes['S']) == len(indexes['X']) and len(indexes['S']) == len(indexes['y']))
            assert (max(indexes['S']) == max(indexes['X']) and max(indexes['S']) == max(indexes['y']))
            assert (min(indexes['S']) == min(indexes['X']) and min(indexes['S']) == min(indexes['y']))

            S_path = os.path.join(ds_path, "S_{}_{}.dat".format(step, n_samples_dict[step]))
            X_path = os.path.join(ds_path, "X_{}_{}.dat".format(step, n_samples_dict[step]))
            y_path = os.path.join(ds_path, "y_{}_{}.dat".format(step, n_samples_dict[step]))

            N = 0
            start = 0

            for i in tqdm.tqdm(range(len(indexes['S']))):
                S_path_curr = os.path.join(ds_path, current_step_files['S'][str(i)])
                X_path_curr = os.path.join(ds_path, current_step_files['X'][str(i)])
                y_path_curr = os.path.join(ds_path, current_step_files['y'][str(i)])

                S_curr = np.memmap(S_path_curr, dtype=np.dtype('U64'), mode="r+")
                N_curr = S_curr.shape[0]
                print(N_curr)

                end = start + N_curr
                N += N_curr

                X_curr = np.memmap(X_path_curr, dtype=np.float32, mode="r+", shape=(N_curr, features_dim))
                y_curr = np.memmap(y_path_curr, dtype=np.float32, mode="r+", shape=(N_curr, labels_dim))

                S = np.memmap(S_path, dtype=np.dtype('U64'), mode="w+", shape=(N,))
                X = np.memmap(X_path, dtype=np.float32, mode="w+", shape=(N, features_dim))
                y = np.memmap(y_path, dtype=np.float32, mode="w+", shape=(N, labels_dim))

                S[start:end] = S_curr
                X[start:end] = X_curr
                y[start:end] = y_curr

                # update starting index
                start = end

                del S_curr, X_curr, y_curr, S, X, y
                os.remove(S_path_curr)
                os.remove(X_path_curr)
                os.remove(y_path_curr)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
