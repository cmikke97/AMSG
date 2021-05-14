import configparser  # implements a basic configuration language for Python programs
import os  # Provides a portable way of using operating system dependent functionality
import sys  # System-specific parameters and functions
from copy import deepcopy  # creates a new object and recursively copies the original object elements

import baker  # Easy, powerful access to Python functions from the command line
import numpy as np  # The fundamental package for scientific computing with Python
import pandas as pd  # Pandas is a flexible and easy to use open source data analysis and manipulation tool
import torch  # Tensor library like NumPy, with strong GPU support
import tqdm  # Instantly makes loops show a smart progress meter
from logzero import logger  # Robust and effective logging for Python

from utils.dataset import Dataset
from utils.fresh_generators import get_generator
from utils.nets import JointEmbeddingNet

# get config file path
joint_embedding_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(joint_embedding_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file
device = config['jointEmbedding']['device']


def detach_and_copy_array(array):  # numpy array or pytorch tensor to copy
    """ Detach numpy array or pytorch tensor and return a deep copy of it.

    Args:
        array: Numpy array or pytorch tensor to copy
    Returns:
        Deep copy of the array
    """

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
    """ Take a set of results dicts and break them out into a single dict of 1d arrays with appropriate column names that
    pandas can convert to a DataFrame.

    Args:
        results_dict: Results (predicted labels) dictionary
    Returns:
        Dictionary containing embeddings
    """
    # a lot of deepcopies are done here to avoid a FD "leak" in the dataset generator
    # see here: https://github.com/pytorch/pytorch/issues/973#issuecomment-459398189

    rv = {}

    for column in range(32):  # for all the tags
        # normalize predicted tag array and save it into rv
        rv['embed_{}'.format(column)] = detach_and_copy_array(results_dict['embedding'][:, column])

    return rv


@baker.command
def get_embedding(results_dir,  # the directory to which to write the 'results.csv' file
                  checkpoint_path,  # path containing the model checkpoints
                  ds_path):  # path of the directory where to find the fresh dataset (containing .dat files)
    """
    Take a trained feedforward neural network model and output evaluation results to a csv in the specified location.

    Args:
        results_dir: The directory to which to write the 'results.csv' file; WARNING -- this will overwrite any
                     existing results in that location
        checkpoint_path: Path containing the model checkpoints
        ds_path: Path of the directory where to find the fresh dataset (containing .dat files)
    """

    # create result directory if it did not already exist
    os.makedirs(results_dir, exist_ok=True)

    # create malware-NN model
    model = JointEmbeddingNet(use_malware=False,
                              use_counts=False,
                              n_tags=len(Dataset.tags),
                              feature_dimension=2381,
                              embedding_dimension=32)

    # load model parameters from checkpoint; if it returns 1 (next epoch to run) it means no checkpoint was found
    if model.load(checkpoint_path) == 1:
        logger.error("No model checkpoint was found in dir {}.".format(checkpoint_path))
        sys.exit(1)

    # allocate model to selected device (CPU or GPU)
    model.to(device)

    # create test generator (a.k.a. test Dataloader)
    generator = get_generator(ds_root=ds_path,
                              return_shas=True,
                              shuffle=False)

    logger.info('Generating Embedding for fresh dataset..')

    # open results file in write mode
    with open(os.path.join(results_dir, 'fresh_dataset_embeddings.csv'), 'w') as dest_file:
        first_batch = True
        # for all the batches in the generator (Dataloader)
        for shas, features, labels in tqdm.tqdm(generator):
            features = features.to(device)  # transfer features to selected device

            # perform a forward pass through the network and get predictions
            predictions = model.get_embedding(features)

            # normalize the resulting embeddings
            results = normalize_embeddings(predictions)

            # add labels and families to the results dict
            results['label'] = labels
            results['family'] = [generator.dataset.label_to_sig(label=label) for label in labels]

            # store results into a pandas dataframe (indexed by the sha265 keys)
            # and then save it as csv into file f (inserting the header only if this is the first batch in the loop)
            pd.DataFrame(results, index=shas).to_csv(dest_file, header=first_batch)

            first_batch = False

    logger.info('Done.')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
