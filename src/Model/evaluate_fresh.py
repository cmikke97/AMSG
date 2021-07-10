import configparser  # implements a basic configuration language for Python programs
import importlib  # provides the implementation of the import statement in Python source code
import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import random  # implements pseudo-random number generators
import sys  # system-specific parameters and functions
import tempfile  # used to create temporary files and directories
from copy import deepcopy  # creates a new object and recursively copies the original object elements

import baker  # easy, powerful access to Python functions from the command line
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import pandas as pd  # pandas is a flexible and easy to use open source data analysis and manipulation tool
import torch  # tensor library like NumPy, with strong GPU support
from logzero import logger  # robust and effective logging for Python
from tqdm import tqdm  # instantly makes loops show a smart progress meter

from nets.generators.fresh_dataset import Dataset
from nets.generators.fresh_generators import get_generator
from utils.ranking_metrics import (mean_reciprocal_rank, mean_average_precision,
                                   max_reciprocal_rank_index, min_reciprocal_rank_index,
                                   max_average_precision_index, min_average_precision_index)

# get config file path
model_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(model_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file
device = config['jointEmbedding']['device']

try:
    # try getting layer sizes from config file
    layer_sizes = json.loads(config['jointEmbedding']['layer_sizes'])
except json.JSONDecodeError:
    # if the option is not present in the config file set layer sizes to None
    layer_sizes = None

# instantiate run additional parameters dict setting values got from config file
run_additional_params = {
    'layer_sizes': layer_sizes,
    'dropout_p': float(config['jointEmbedding']['dropout_p']),
    'activation_function': config['jointEmbedding']['activation_function']
}


# network type (possible values: jointEmbedding, JointEmbedding_cosine, JointEmbedding_pairwise_distance, detectionBase)
def import_modules(net_type):
    """ Dynamically import network depending on the provided argument.

    Args:
        net_type: Network type (possible values: jointEmbedding, JointEmbedding_cosine,
                  JointEmbedding_pairwise_distance, detectionBase)
    Returns:
        Net imported from selected modules.
    """

    # set network module name based on the current network type
    if net_type.lower() == 'jointembedding':
        net_type = 'jointEmbedding'
        net_module_name = "nets.JointEmbedding_net"
    elif net_type.lower() == 'jointembedding_cosine':
        net_type = 'jointEmbedding'
        net_module_name = "nets.JointEmbedding_net_cosine"
    elif net_type.lower() == 'jointembedding_pairwise_distance':
        net_type = 'jointEmbedding'
        net_module_name = "nets.JointEmbedding_net_pairwise_distance"
    else:  # if the network type is neither JointEmbedding nor DetectionBase raise ValueError
        raise ValueError('Unknown Network type. Possible values: "JointEmbedding", "jointEmbedding_cosine" or '
                         '"jointEmbedding_pairwise_distance". Got {} '
                         .format(net_type))

    # import net module
    net_module = importlib.import_module(net_module_name)
    # get 'Net' class from net module
    Net = getattr(net_module, 'Net')

    # return classes, functions and variables imported
    return Net


def detach_and_copy_array(array):  # numpy array or pytorch tensor to copy
    """ Detach numpy array or pytorch tensor and return a deep copy of it.

    Args:
        array: Numpy array or pytorch tensor to copy
    Returns:
        Deep copy of the array.
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
        Dictionary containing embeddings.
    """
    # a lot of deepcopies are done here to avoid a FD "leak" in the dataset generator
    # see here: https://github.com/pytorch/pytorch/issues/973#issuecomment-459398189

    rv = {}

    for column in range(32):  # for all the tags
        # normalize predicted tag array and save it into rv
        rv['embed_{}'.format(column)] = detach_and_copy_array(results_dict['embedding'][:, column])

    return rv


def evaluate_fresh_predictions(ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                               checkpoint_path,  # path to the model checkpoint to load
                               # network to use between 'JointEmbedding', 'JointEmbedding_cosine',
                               # 'JointEmbedding_pairwise_distance' and 'DetectionBase'
                               net_type='JointEmbedding',
                               n_anchor_samples_per_family=10,
                               batch_size=1000):  # how many samples per batch to load

    # dynamically import some classes, functions and variables from modules depending on the current net and gen types
    Net = import_modules(net_type=net_type)

    # create JointEmbeddingNet model
    model = Net(use_malware=False,
                use_counts=False,
                n_tags=len(Dataset.tags),
                feature_dimension=2381,
                embedding_dimension=32,
                layer_sizes=run_additional_params['layer_sizes'],
                dropout_p=run_additional_params['dropout_p'],
                activation_function=run_additional_params['activation_function'])

    # load model parameters from checkpoint
    model.load_state_dict(torch.load(checkpoint_path))

    # allocate model to selected device (CPU or GPU)
    model.to(device)

    # set the model mode to 'eval'
    model.eval()

    # create fresh dataset generator
    generator = get_generator(ds_root=ds_path,
                              batch_size=batch_size,
                              return_shas=True,
                              shuffle=True)  # shuffle samples

    # get label to signature function from the dataset (used to convert numerical labels to family names)
    label_to_sig = generator.dataset.label_to_sig

    n_families = generator.dataset.n_families

    if n_anchor_samples_per_family * n_families >= generator.dataset.__len__():
        raise ValueError('number of anchor samples selected is too high.')

    anchors = None
    anchors_families = [0 for _ in range(n_families)]

    # for all the batches in the generator (Dataloader)
    for shas, features, labels in generator:
        # transfer features to selected device
        features = features.to(device)

        # perform a forward pass through the network and get predictions
        predictions = model.get_embedding(features)

        # get embeddings
        embeddings = predictions['embedding']

        for n in range(n_families):
            if anchors_families[n] >= n_families:
                continue

            indices = [i for i, label in enumerate(labels) if label == n]
            indices = indices[:n_anchor_samples_per_family] if len(indices) > n_anchor_samples_per_family else indices
            logger.info(indices)

            if anchors is None:
                anchors = {
                    'shas': shas[indices],
                    'labels': labels[indices],
                    'embeddings': embeddings[indices]
                }
            else:
                anchors['shas'].append(shas[indices])
                anchors['labels'] = torch.cat((anchors['labels'], labels[indices]), 0)
                anchors['embeddings'] = torch.cat((anchors['embeddings'], embeddings[indices]), 0)

            anchors_families[int(labels[n])] += len(indices)

        if all(n >= n_families for n in anchors_families):
            break

    # for all the batches in the generator (Dataloader)
    for shas, features, labels in tqdm(generator):
        indices = [i for i, sha in enumerate(shas) if sha not in anchors['shas']]

        selected_shas = shas[indices]
        selected_features = features[indices]
        selected_labels = labels[indices]

        # transfer features to selected device
        selected_features = selected_features.to(device)

        # perform a forward pass through the network and get predictions
        predictions = model.get_embedding(selected_features)

        # get embeddings
        embeddings = predictions['embedding']

        # compute similarities between the queries samples' embeddings and the whole batch's embeddings
        rv = model.get_similarity(embeddings, anchors['embeddings'])

        # get similarities
        similarities = rv['similarity'].cpu().detach()

        probabilities = rv['probability'].cpu().detach()

        print('similarities')
        print('shape: ({})'.format(similarities.shape))
        print(similarities[:5])
        print('probabilities')
        print('shape: ({})'.format(probabilities.shape))
        print(probabilities[:5])


def evaluate_fresh_rankings(ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                            checkpoint_path,  # path to the model checkpoint to load
                            # network to use between 'JointEmbedding', 'JointEmbedding_cosine',
                            # 'JointEmbedding_pairwise_distance' and 'DetectionBase'
                            net_type='JointEmbedding',
                            n_queries=100,  # number of queries to do
                            batch_size=1000):  # how many samples per batch to load
    """ Take a trained feedforward neural network model and output fresh dataset evaluation results to a csv file.

    Args:
        ds_path: Path of the directory where to find the fresh dataset (containing .dat files)
        checkpoint_path: Path to the model checkpoint to load
        net_type: Network to use between 'JointEmbedding', 'JointEmbedding_cosine', 'JointEmbedding_pairwise_distance'
                  and 'DetectionBase'. (default: 'JointEmbedding')
        n_queries: Number of queries to do (default: 100)
        batch_size: How many samples per batch to load (default: 1000)
    """

    # dynamically import some classes, functions and variables from modules depending on the current net and gen types
    Net = import_modules(net_type=net_type)

    # if the number of queries q is greater than the batch size -> error
    if n_queries > batch_size:
        logger.error("Batch size must be greater than the number of queries 'q'.")
        sys.exit(1)

    # create JointEmbeddingNet model
    model = Net(use_malware=False,
                use_counts=False,
                n_tags=len(Dataset.tags),
                feature_dimension=2381,
                embedding_dimension=32,
                layer_sizes=run_additional_params['layer_sizes'],
                dropout_p=run_additional_params['dropout_p'],
                activation_function=run_additional_params['activation_function'])

    # load model parameters from checkpoint
    model.load_state_dict(torch.load(checkpoint_path))

    # allocate model to selected device (CPU or GPU)
    model.to(device)

    # set the model mode to 'eval'
    model.eval()

    # create fresh dataset generator
    generator = get_generator(ds_root=ds_path,
                              batch_size=batch_size,
                              return_shas=True,
                              shuffle=True)  # shuffle samples

    # get label to signature function from the dataset (used to convert numerical labels to family names)
    label_to_sig = generator.dataset.label_to_sig

    # set queries and rank_per_query dicts to null value
    queries = None
    rank_per_query = {}
    # for all the batches in the generator (Dataloader)
    for shas, features, labels in tqdm(generator):

        # transfer features to selected device
        features = features.to(device)

        # perform a forward pass through the network and get predictions
        predictions = model.get_embedding(features)

        # get embeddings
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
        rv = model.get_similarity(queries['embeddings'], embeddings)

        # get similarities
        similarities = rv['similarity'].cpu().detach()

        # get ranks per query sample:
        # for each query sample -> order samples labels/shas based on the similarity measure
        # (skipping position 0 because it contains the label/sha of the current query sample)
        rank_per_query.update({
            i: {
                'query_sha': s,
                'ground_truth_label': int(queries['labels'][i].item()),
                'ground_truth_family': label_to_sig(int(queries['labels'][i].item())),
                'rank_shas': np.asarray(shas, dtype=np.dtype('U64'))[similarities[i, :].argsort()[1:]].tolist(),
                'rank_labels': [int(lab) for lab in labels[similarities[i, :].argsort()[1:]]],
                'rank_families': [label_to_sig(int(lab.item()))
                                  for lab in labels[similarities[i, :].argsort()[1:]]]
            } for i, s in enumerate(queries['shas'])
        })

    logger.info('Calculating results..')

    # compute binarized (0/1) relevance scores
    rs = [np.asarray([i == rank['ground_truth_label'] for i in rank['rank_labels']], dtype=np.dtype(int))
          for rank in rank_per_query.values()]

    # compute and log MRR and MAP scores
    mlflow.log_metric('MRR', mean_reciprocal_rank(rs))
    mlflow.log_metric('MAP', mean_average_precision(rs))

    # compute a bunch of indexes for interesting queries to save in csv files as examples
    queries_indexes = {
        'max_rr': max_reciprocal_rank_index(rs),
        'min_rr': min_reciprocal_rank_index(rs),
        'max_ap': max_average_precision_index(rs),
        'min_ap': min_average_precision_index(rs),
        'random': random.choice([v for v in range(len(rank_per_query.keys()))
                                 if v not in [max_reciprocal_rank_index(rs),
                                              min_reciprocal_rank_index(rs),
                                              max_average_precision_index(rs),
                                              min_average_precision_index(rs)]])
    }

    # get interesting queries
    ranks_to_save = {
        key: rank_per_query[index]
        for key, index in queries_indexes.items()
    }

    # compute example ranks dataframes
    dataframes = {
        key: pd.DataFrame({"sha256": rank['rank_shas'],
                           "label": rank['rank_labels'],
                           "family": rank['rank_families']})
        for key, rank in ranks_to_save.items()
    }

    # compute example ranks metadata
    metadata = {
        key: pd.Series([
            'Query sample sha256: {}'.format(rank['query_sha']),
            'Ground truth label: {}'.format(rank['ground_truth_label']),
            'Ground truth family: {}'.format(rank['ground_truth_family'])
        ])
        for key, rank in ranks_to_save.items()
    }

    logger.info('Saving results..')

    # create temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        # set result file filename
        filename = os.path.join(tempdir, 'fresh_dataset_rankings.json')

        # save rankings to file
        with open(filename, 'w') as dest_file:
            json.dump(rank_per_query, dest_file)

        # log json file
        mlflow.log_artifact(filename, 'results')

        # for each example rank
        for df_key, df_val in dataframes.items():
            # retrieve metadata
            meta = metadata[df_key]

            # create file name
            df_filename = os.path.join(tempdir, '{}_example_rank.csv'.format(df_key))

            # open dataframe dest file and write both metadata and dataframe to it
            with open(df_filename, 'w') as df_f:
                meta.to_csv(df_f, index=False)
                df_val.to_csv(df_f)

            # log example rank
            mlflow.log_artifact(df_filename, 'results')

    logger.info('Done.')


@baker.command
def evaluate_fresh(ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                   checkpoint_path,  # path to the model checkpoint to load
                   # network to use between 'JointEmbedding', 'JointEmbedding_cosine',
                   # 'JointEmbedding_pairwise_distance' and 'DetectionBase'
                   net_type='JointEmbedding',
                   n_anchor_samples_per_family=10,
                   n_queries=100,  # number of queries to do
                   batch_size=1000):  # how many samples per batch to load
    # start mlflow run
    with mlflow.start_run():
        evaluate_fresh_predictions(ds_path=ds_path,
                                   checkpoint_path=checkpoint_path,
                                   net_type=net_type,
                                   n_anchor_samples_per_family=n_anchor_samples_per_family,
                                   batch_size=batch_size)

        evaluate_fresh_rankings(ds_path=ds_path,
                                checkpoint_path=checkpoint_path,
                                net_type=net_type,
                                n_queries=n_queries,
                                batch_size=batch_size)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
