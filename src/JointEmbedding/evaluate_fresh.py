import configparser  # implements a basic configuration language for Python programs
import os  # Provides a portable way of using operating system dependent functionality
import sys  # System-specific parameters and functions
import tempfile  # used to create temporary files and directories
from copy import deepcopy  # creates a new object and recursively copies the original object elements

import baker  # Easy, powerful access to Python functions from the command line
import mlflow
import numpy as np  # The fundamental package for scientific computing with Python
import pandas as pd  # Pandas is a flexible and easy to use open source data analysis and manipulation tool
import torch  # Tensor library like NumPy, with strong GPU support
import tqdm  # Instantly makes loops show a smart progress meter
from logzero import logger  # Robust and effective logging for Python

from utils.dataset import Dataset
from utils.fresh_generators import get_generator
from utils.nets import JointEmbeddingNet
from utils.ranking_metrics import mean_reciprocal_rank, mean_average_precision

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
    """ Take a set of results dicts and break them out into a single dict of 1d arrays with appropriate column names
    that pandas can convert to a DataFrame.

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
def evaluate_fresh(ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                   checkpoint_path,  # path containing the model checkpoints
                   n_queries=100,  # number of queries to do
                   batch_size=1000):  # how many samples per batch to load
    """ Take a trained feedforward neural network model and output fresh dataset evaluation results to a csv file.

    Args:
        ds_path: Path of the directory where to find the fresh dataset (containing .dat files)
        checkpoint_path: Path containing the model checkpoints
        n_queries: Number of queries to do (default: 100)
        batch_size: How many samples per batch to load (default: 1000)
    """
    # start mlflow run
    with mlflow.start_run():
        # if the number of queries q is greater than the batch size -> error
        if n_queries > batch_size:
            logger.error("Batch size must be greater than the number of queries 'q'.")
            sys.exit(1)

        # create JointEmbeddingNet model
        model = JointEmbeddingNet(use_malware=False,
                                  use_counts=False,
                                  n_tags=len(Dataset.tags),
                                  feature_dimension=2381,
                                  embedding_dimension=32)

        # load model parameters from checkpoint
        model.load_state_dict(torch.load(checkpoint_path))

        # allocate model to selected device (CPU or GPU)
        model.to(device)

        # create fresh dataset generator
        generator = get_generator(ds_root=ds_path,
                                  batch_size=batch_size,
                                  return_shas=True,
                                  shuffle=True)  # shuffle samples

        # get label to signature function from the dataset (used to convert numerical labels to family names)
        label_to_sig = generator.dataset.label_to_sig

        # create temporary directory
        with tempfile.TemporaryDirectory() as tempdir:
            # set result file filename
            filename = os.path.join(tempdir, 'fresh_dataset_rankings.csv')

            # open file in write mode
            with open(filename, 'w') as dest_file:
                # set queries and rank_per_query dicts to null value
                queries = None
                rank_per_query = {}
                # for all the batches in the generator (Dataloader)
                for shas, features, labels in tqdm.tqdm(generator):
                    # transfer features to selected device
                    features = features.to(device)

                    # perform a forward pass through the network and get predictions
                    predictions = model.get_embedding(features)

                    embeddings = predictions['embedding']

                    # if it's the first iteration (query is none)
                    if queries is None:
                        # initialize queries dict getting the first q (shuffled) samples
                        queries = {
                            'shas': shas[:n_queries],
                            'embeddings': embeddings[:n_queries],
                            'labels': labels[:n_queries]
                        }

                    # compute similarities between the queries samples' embeddings and the whole batch's embeddings
                    similarities = model.get_similarity(queries['embeddings'], embeddings)

                    # get ranks per query sample:
                    # for each query sample -> order samples labels/shas based on the similarity measure
                    # (skipping position 0 because it contains the label/sha of the current query sample)
                    rank_per_query.update({
                        s: {
                            'rank_labels': labels[similarities[i, :].argsort()[1:]],
                            'rank_shas': shas[similarities[i, :].argsort()[1:]],
                            'ground_truth_label': queries['labels'][i]
                        } for i, s in enumerate(queries['shas'])
                    })

                # compute binarized (0/1) relevance scores
                rs = [np.asarray(rank['rank_labels'] == rank['ground_truth_label'], dtype=np.dtype(int))
                      for rank in rank_per_query.values()]

                # compute and log MRR and MAP scores
                mlflow.log_metric('MRR', mean_reciprocal_rank(rs))
                mlflow.log_metric('MAP', mean_average_precision(rs))

                # prepare dataframe indexes:
                # for each query sample, prepare a couple of headers (sha, label)
                indx = [v for s, val in rank_per_query.items()
                        for v in [(s, 'sha'),
                                  (s, 'label (GT: {}="{}")'.format(val['ground_truth_label'],
                                                                   label_to_sig(val['ground_truth_label'])))]]

                # prepare dataframe data:
                # for each query sample, get its ranked shas and then its ranked labels
                data = [v for val in rank_per_query.values()
                        for v in [val['rank_shas'],
                                  "{}='{}'".format(val['rank_labels'], label_to_sig(val['ground_truth_label']))]]

                # create dataframe, transpose it and save it to csv file
                pd.DataFrame(data, index=indx).T.to_csv(dest_file, header=True)

                # log saved dataframe
                mlflow.log_artifact(filename, 'results')

        logger.info('Done.')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
