import os  # Provides a portable way of using operating system dependent functionality
# Used to construct a new compound object and then, recursively, insert copies into it of the objects
# found in the original
from copy import deepcopy

import baker  # Easy, powerful access to Python functions from the command line
import numpy as np  # The fundamental package for scientific computing with Python
# Pandas is a fast, powerful, flexible and easy to use open source data analysis and manipulation tool
import pandas as pd
import torch  # Tensor library like NumPy, with strong GPU support
import tqdm  # Instantly makes loops show a smart progress meter
from logzero import logger  # Robust and effective logging for Python
from waiting import wait

import config  # import config.py
from dataset import Dataset  # import Dataset.py
from generators import get_generator  # import get_generator function from Generators.py
from nets import JointEmbeddingNet  # import JointEmbeddingNet from Nets.py

# get tags from the dataset
all_tags = Dataset.tags


def detach_and_copy_array(array):  # utility function to detach and (deep) copy an array
    if isinstance(array, torch.Tensor):  # if the provided array is of type Tensor
        # return a copy of the array after having detached it, passed it to the cpu and finally flattened
        return deepcopy(array.cpu().detach().numpy()).ravel()
    elif isinstance(array, np.ndarray):  # else if it is of type ndarray
        # return a copy of the array after having flattened it
        return deepcopy(array).ravel()
    else:
        # otherwise raise an exception
        raise ValueError("Got array of unknown type {}".format(type(array)))


def normalize_embeddings(results_dict):  # results (predicted labels) dictionary
    """
    Take a set of results dicts and break them out into
    a single dict of 1d arrays with appropriate column names
    that pandas can convert to a DataFrame.
    """
    # we do a lot of deepcopy stuff here to avoid a FD "leak" in the dataset generator
    # see here: https://github.com/pytorch/pytorch/issues/973#issuecomment-459398189

    rv = {}

    for column in range(32):  # for all the tags
        # normalize predicted tag array and save it into rv
        rv[f'embedding_{column}'] = detach_and_copy_array(results_dict['similarity'][:, column])

    return rv


@baker.command
def get_embedding(results_dir,  # The directory to which to write the 'results.csv' file
                  checkpoint_file,  # The checkpoint file containing the weights to evaluate
                  db_path=config.db_path,  # The path to the directory containing the meta.db file
                  mode='train',  # mode of use of the dataset object (may be 'train', 'validation' or 'test')
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
    Take a trained feedforward neural network model and output evaluation results to a csv in the specified location.
    :param results_dir: The directory to which to write the 'results.csv' file; WARNING -- this will overwrite any
        existing results in that location
    :param checkpoint_file: The checkpoint file containing the weights to evaluate
    :param mode: mode of use of the dataset object (may be 'train', 'validation' or 'test')
    :param db_path: the path to the directory containing the meta.db file; defaults to the value in config.py
    :param remove_missing_features: See help for remove_missing_features in train.py / train_network
    """

    # create result directory
    os.system('mkdir -p {}'.format(results_dir))

    # wait until checkpoint directory is fully created (needed when using a Drive as results storage)
    wait(lambda: os.path.exists(results_dir))

    # create malware-NN model
    model = JointEmbeddingNet(use_malware=False,
                              use_counts=False,
                              n_tags=len(Dataset.tags),  # get n_tags counting tags from the dataset
                              feature_dimension=2381,
                              embedding_dimension=32)

    # load model parameters from checkpoint
    model.load_state_dict(torch.load(checkpoint_file))

    # allocate model to selected device (CPU or GPU)
    model.to(config.device)

    # create test generator (a.k.a. test Dataloader)
    generator = get_generator(mode=mode,
                              path=db_path,
                              use_malicious_labels=False,
                              use_count_labels=False,
                              use_tag_labels=True,
                              return_shas=True,  # return sha256 keys
                              n_samples=config.test_n_samples_max,
                              remove_missing_features=remove_missing_features)

    # log info
    logger.info('...running network prediction')

    # create and open the results file in write mode
    f = open(os.path.join(results_dir, mode + '_prediction.csv'), 'w')

    first_batch = True
    # for all the batches in the generator (Dataloader)
    for shas, features, labels in tqdm.tqdm(generator):
        features = features.to(config.device)  # transfer features to selected device

        # perform a forward pass through the network and get predictions
        predictions = model.get_embedding(features)

        # normalize the results
        results = normalize_embeddings(predictions)

        # store results into a pandas dataframe (indexed by the sha265 keys)
        # and then save it as csv into file f (inserting the header only if this is the first batch in the loop)
        pd.DataFrame(results, index=shas).to_csv(f, header=first_batch)

        first_batch = False
    f.close()  # close results file
    logger.info('...done')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
