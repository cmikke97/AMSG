import os

import baker  # Easy, powerful access to Python functions from the command line
import numpy as np
import tqdm  # Instantly makes loops show a smart progress meter
from logzero import logger  # Robust and effective logging for Python
from waiting import wait

from src.JointEmbedding.generators import get_generator  # import get_generator function from Generators.py
from src.EmberFeaturesExtractor.features import PEFeatureExtractor
from src.JointEmbedding.sorel_dataset import Dataset

steps = ['train', 'validation', 'test']
feature_version = 2


@baker.command
def preprocess_dataset(db_path,  # The path to the directory containing the meta.db file
                       destination_dir,  # The directory to which to write the 'results.csv' file
                       training_n_samples=-1,  # max number of training data samples to use (if -1 -> takes all)
                       validation_n_samples=-1,  # max number of validation data samples to use (if -1 -> takes all)
                       test_n_samples=-1,  # max number of test data samples to use (if -1 -> takes all)
                       batch_size=8192,  # how many samples per batch to load
                       # How many worker processes should the dataloader use (if None use multiprocessing.cpu_count())
                       workers=None,
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
                       remove_missing_features='scan'):

    """
    Pre-process Sorel20M dataset.
    """

    # instantiate key-n_samples dict
    n_samples = {'train': training_n_samples,
                 'validation': validation_n_samples,
                 'test': test_n_samples}

    # instantiate the train, valid and test dataloaders
    dataloaders = {key: get_generator(path=db_path,
                                      mode=key,
                                      use_malicious_labels=True,
                                      use_count_labels=True,
                                      use_tag_labels=True,
                                      batch_size=batch_size,
                                      num_workers=workers,
                                      return_shas=True,
                                      n_samples=n_samples[key],
                                      remove_missing_features=remove_missing_features) for key in steps}

    # create result directory
    os.makedirs(destination_dir, exist_ok=True)

    # wait until destination_dir is fully created (needed when using a Drive as results storage)
    wait(lambda: os.path.exists(destination_dir))

    # instantiate PE feature extractor
    extractor = PEFeatureExtractor(feature_version, print_feature_warning=False)

    # for each key (train, validation and test)
    for key in dataloaders.keys():
        logger.info('Now processing {} dataset...'.format(key))

        # generate X (features vector) and y (labels vector) file names
        X_path = os.path.join(destination_dir, "X_{}.dat".format(key))
        y_path = os.path.join(destination_dir, "y_{}.dat".format(key))

        # get total number of samples in the dataset
        n_samples = len(dataloaders[key].dataset)

        # instantiate labels dimension as 1 (malware) + 1 (count) + n_tags (tags)
        labels_dim = 1 + 1 + len(Dataset.tags)

        # Create space on disk to write features (and labels) to
        X = np.memmap(X_path, dtype=np.float32, mode="w+", shape=(n_samples, extractor.dim))
        y = np.memmap(y_path, dtype=np.float32, mode="w+", shape=(n_samples, labels_dim))
        # delete X and y vectors -> this will flush the memmap instance writing the changes to the files
        del X, y

        with open(os.path.join(destination_dir, 'shas_{}.txt'.format(key)), 'w') as meta:

            # initialize labels (y) and feature vectors (x) starting indexes
            y_start = 0
            x_start = 0
            for shas, features, labels in tqdm.tqdm(dataloaders[key]):
                current_batch_size = len(shas)

                # open y memory map in Read+ mode
                y = np.memmap(y_path, dtype=np.float32, mode="r+", shape=(n_samples, labels_dim))
                # compute labels ending index
                y_end = y_start + current_batch_size
                # save current labels
                y[y_start:y_end] = labels
                # update labels starting index
                y_start += current_batch_size

                # open X memory map in Read+ mode
                X = np.memmap(X_path, dtype=np.float32, mode="r+", shape=(n_samples, extractor.dim))
                # compute feature vectors ending index
                x_end = x_start + current_batch_size
                # save current feature vectors
                X[x_start:x_end] = features
                # update feature vectors starting index
                x_start += current_batch_size

                for sha in shas:
                    meta.write('{}\n'.format(sha))


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
