import os

import baker  # Easy, powerful access to Python functions from the command line
import numpy as np
import pyxis as px
import tqdm  # Instantly makes loops show a smart progress meter
from logzero import logger  # Robust and effective logging for Python
from waiting import wait

import config  # import config.py
from generators import get_generator  # import get_generator function from Generators.py

steps = ['train', 'validation', 'test']


@baker.command
def preprocess_dataset(destination_dir,  # The directory to which to write the 'results.csv' file
                       db_path=config.db_path,  # The path to the directory containing the meta.db file
                       use_malicious_labels=False,  # Whether or not to record malware labels and predictions
                       use_count_labels=False,  # Whether or not to record count labels and predictions
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

    dataloaders = {key: get_generator(mode=key,  # select test mode
                                      path=db_path,
                                      use_malicious_labels=use_malicious_labels,
                                      use_count_labels=use_count_labels,
                                      use_tag_labels=True,
                                      return_shas=True,  # return sha256 keys
                                      # n_samples=1000,
                                      remove_missing_features=remove_missing_features) for key in steps}

    # create result directory
    os.system('mkdir -p {}'.format(destination_dir))

    # wait until checkpoint directory is fully created (needed when using a Drive as results storage)
    wait(lambda: os.path.exists(destination_dir))

    for key in dataloaders:
        # log info
        logger.info('...running ' + key + '_data preprocessing')

        db = px.Writer(dirpath=os.path.join(destination_dir, key + '_data'),  map_size_limit=80000)

        # for all the batches in the generator (Dataloader)
        for shas, features, labels in tqdm.tqdm(dataloaders[key]):
            db.put_samples('shas',
                           np.asarray(shas),
                           'features',
                           np.asarray(features),
                           'malware_labels',
                           np.asarray(labels['malware']),
                           'count_labels',
                           np.asarray(labels['count']),
                           'tags_labels',
                           np.asarray(labels['tags']))

        db.close()


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()