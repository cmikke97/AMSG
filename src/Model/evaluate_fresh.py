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
import torch.nn.functional as F  # pytorch neural network functional interface
from logzero import logger  # robust and effective logging for Python
from tqdm import tqdm  # instantly makes loops show a smart progress meter

from nets.generators.fresh_dataset import Dataset
from nets.generators.fresh_generators import get_generator
from nets.generators.generators_alt3 import get_generator as sorel_get_generator
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


def distance_to_similarity(distances,  # tensor containing the distances calculated between two embeddings
                           a=1.0,  # inversion multiplication factor
                           function='exp'):  # inversion function to use. Possible values are: 'exp', 'inv' or 'inv_pow'
    """ Calculate similarity scores from distances by using an inversion function.

    Args:
        distances: Tensor containing the distances calculated between two embeddings
        a: Inversion multiplication factor
        function: Inversion function to use. Possible values are: 'exp', 'inv' or 'inv_pow'
    Returns:
        Similarity scores computed from the provided distances.
    """

    if function == 'exp':
        similarity = torch.exp(torch.div(distances, -a))
    elif function == 'inv':
        similarity = torch.pow(torch.add(torch.div(distances, a), 1.0), -1.0)
    elif function == 'inv_pow':
        similarity = torch.pow(torch.add(torch.div(torch.pow(distances, 2.0), a), 1.0), -1.0)
    else:
        raise ValueError('Unknown distance-to-similarity function {}.'.format(function))
    return similarity


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
        net_module_name = 'nets.JointEmbedding_net'
        similarity_type = 'dotProduct'
    elif net_type.lower() == 'jointembedding_cosine':
        net_type = 'jointEmbedding'
        net_module_name = 'nets.JointEmbedding_net_cosine'
        similarity_type = 'cosineSimilarity'
    elif net_type.lower() == 'jointembedding_pairwise_distance':
        net_type = 'jointEmbedding'
        net_module_name = 'nets.JointEmbedding_net_pairwise_distance'
        similarity_type = 'invertedEuclideanDistance'
    else:  # if the network type is neither JointEmbedding nor DetectionBase raise ValueError
        raise ValueError('Unknown Network type. Possible values: "JointEmbedding", "jointEmbedding_cosine" or '
                         '"jointEmbedding_pairwise_distance". Got {} '
                         .format(net_type))

    # import net module
    net_module = importlib.import_module(net_module_name)
    # get 'Net' class from net module
    Net = getattr(net_module, 'Net')

    # return classes, functions and variables imported
    return Net, similarity_type


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
                               # how many anchor samples to use in the family prediction task
                               n_anchor_samples_per_family=10,
                               # whether to perform a 'hard' (True) or 'soft' (False) malware family prediction
                               hard=False,
                               batch_size=1000):  # how many samples per batch to load
    """ Evaluates the model on the family prediction task. It selects n anchor samples per family and then uses those
    to assign a family label to all the other samples in the fresh dataset and evaluates the performance on this task.

    Args:
        ds_path: Path of the directory where to find the fresh dataset (containing .dat files)
        checkpoint_path: Path to the model checkpoint to load
        net_type: Network to use between 'JointEmbedding', 'JointEmbedding_cosine',
                    'JointEmbedding_pairwise_distance' and 'DetectionBase'
        n_anchor_samples_per_family: How many anchor samples to use in the family prediction task (default: 10)
        hard: Whether to perform a 'hard' (True) or 'soft' (False) malware family prediction (default: False)
        batch_size: How many samples per batch to load
    """

    # dynamically import some classes, functions and variables from modules depending on the current net and gen types
    Net, similarity_type = import_modules(net_type=net_type)

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

    sorelGenerator = sorel_get_generator(ds_root=ds_path,
                                         batch_size=batch_size,
                                         mode='test',  # select test mode
                                         n_samples=2521,
                                         use_malicious_labels=False,
                                         use_count_labels=False,
                                         use_tag_labels=True,
                                         return_shas=True)

    # create fresh dataset generator
    generator = get_generator(ds_root=ds_path,
                              batch_size=batch_size,
                              return_shas=True,
                              shuffle=True)  # shuffle samples

    with open(os.path.join('content','sorel_results.csv'), 'w') as f:
        first_batch = True
        # for all the batches in the generator (Dataloader)
        for shas, features, labels in sorelGenerator:
            features = features.to(device)  # transfer features to selected device

            # perform a forward pass through the network and get predictions
            predictions = model(features)

            # normalize the results
            results = model.normalize_results(labels,
                                              predictions,
                                              use_malware=False,
                                              use_count=False,
                                              use_tags=True)

            results['features'] = deepcopy(features.cpu().detach().numpy()).ravel()

            # store results into a pandas dataframe (indexed by the sha265 keys) and then save it as csv into
            # file f (inserting the header only if this is the first batch in the loop)
            pd.DataFrame(results, index=shas).to_csv(f, header=first_batch)

            first_batch = False

    # get label to signature function from the dataset (used to convert numerical labels to family names)
    label_to_sig = generator.dataset.label_to_sig

    # get total number of families
    n_families = generator.dataset.n_families

    # if the total number of anchor samples is greater than the dataset size, error
    if n_anchor_samples_per_family * n_families >= generator.dataset.__len__():
        raise ValueError('number of anchor samples selected is too high.')

    # initialize anchors to an empty dict and anchor families to a list of zeros representing the number
    # of anchor samples retrieved per family
    anchors = None
    anchors_families = [0 for _ in range(n_families)]

    logger.info('Selecting {} anchor samples per-family..'.format(n_anchor_samples_per_family))

    # for all the batches in the generator (Dataloader)
    for shas, features, labels in generator:
        # transfer features to selected device
        features = features.to(device)

        # perform a forward pass through the network and get predictions
        predictions = model.get_embedding(features)

        # get embeddings
        embeddings = predictions['embedding']

        # for each family
        for n in range(n_families):
            # if the family has at leas n_anchor_samples_per_family anchor samples, go to the next one
            if anchors_families[n] >= n_anchor_samples_per_family:
                continue

            # get the indices of all samples with the same label as the current family
            indices = [i for i, label in enumerate(labels) if label == n]
            # get the first n_anchor_samples_per_family sample indices (or less if there are not enough indices)
            indices = indices[:n_anchor_samples_per_family] if len(indices) > n_anchor_samples_per_family else indices

            # the first iteration assign the first anchor samples' shas, labels and embeddings
            if anchors is None:
                anchors = {
                    'shas': [shas[i] for i in indices],
                    'labels': labels[indices],
                    'embeddings': embeddings[indices]
                }
            else:  # from the second iteration on, instead, append (concatenate) them
                anchors['shas'].extend([shas[i] for i in indices])
                anchors['labels'] = torch.cat((anchors['labels'], labels[indices]), 0)
                anchors['embeddings'] = torch.cat((anchors['embeddings'], embeddings[indices]), 0)

            # update the count of anchor samples for the current family
            anchors_families[n] += len(indices)

        # if all families have at least n_anchor_samples_per_family anchor samples, break
        if all(n >= n_anchor_samples_per_family for n in anchors_families):
            break

    logger.info('Calculating results..')

    with open(os.path.join('content', 'fresh_results.csv'), 'w') as f_res:
        # create temporary directory
        with tempfile.TemporaryDirectory() as tempdir:
            filename = os.path.join(tempdir, 'fresh_results.csv')

            # create and open the fresh results file in write mode
            with open(filename, 'w') as f:
                first_batch = True

                # for all the batches in the generator (Dataloader)
                for shas, features, labels in tqdm(generator):
                    # get the indices of all the anchor samples in the current batch
                    indices = [i for i, sha in enumerate(shas) if sha not in anchors['shas']]

                    # select all non-anchor samples
                    selected_shas = [shas[i] for i in indices]
                    selected_features = features[indices]
                    selected_labels = labels[indices]

                    # transfer features to selected device
                    selected_features = selected_features.to(device)

                    # perform a forward pass through the network and get predictions
                    predictions = model.get_embedding(selected_features)

                    # get embeddings
                    embeddings = predictions['embedding']

                    # if the selected model similarity function is the inverted euclidean distance
                    if similarity_type == 'invertedEuclideanDistance':
                        # compute the similarity scores between the samples and anchors' embeddings using the model's
                        # get_similarity function
                        similarity_scores = model.get_similarity(embeddings, anchors['embeddings'])['similarity'].cpu().detach()
                    else:
                        # compute the similarity scores as the cosine similarity between the samples and anchors' embeddings
                        similarity_scores = torch.div(torch.add(F.cosine_similarity(embeddings.unsqueeze(1),
                                                                                    anchors['embeddings'].unsqueeze(0),
                                                                                    dim=2), 1.0), 2.0).cpu().detach()

                    # initialize result dict
                    rv = {}

                    if hard:
                        # for each family
                        for i in range(n_families):
                            # for each non-anchor sample in the current batch, set current ground truth family label to 1
                            # if the sample has the same label as the current family, to 0 otherwise
                            rv['label_{}'.format(label_to_sig(i))] = [int(lab == i) for lab in selected_labels]
                            # for each non-anchor sample in the current batch, set predicted family label to the max
                            # similarity between the sample and the anchor samples of the current family only for the most
                            # similar family/ies; the other family labels for the sample are set to 0
                            rv['pred_{}'.format(label_to_sig(i))] = [
                                int(torch.max(
                                    sims[[j for j in range(len(sims)) if anchors['labels'][j] == i]]).item() == torch.max(
                                    sims))
                                for sims in similarity_scores]
                    else:
                        for i in range(n_families):
                            # for each non-anchor sample in the current batch, set current ground truth family label to 1
                            # if the sample has the same label as the current family, to 0 otherwise
                            rv['label_{}'.format(label_to_sig(i))] = [int(lab == i) for lab in selected_labels]
                            # for each non-anchor sample in the current batch, set predicted family label to the max
                            # similarity between the sample and the anchor samples of the current family
                            rv['pred_{}'.format(label_to_sig(i))] = [
                                torch.max(sims[[j for j in range(len(sims)) if anchors['labels'][j] == i]]).item() for sims
                                in
                                similarity_scores]

                    # store results into a pandas dataframe (indexed by the sha265 keys) and then save it as csv into
                    # file f (inserting the header only if this is the first batch in the loop)
                    pd.DataFrame(rv, index=selected_shas).to_csv(f, header=first_batch)

                    rv['features'] = deepcopy(features.cpu().detach().numpy()).ravel()
                    pd.DataFrame(rv, index=selected_shas).to_csv(f_res, header=first_batch)

                    first_batch = False

            # log results file as artifact
            mlflow.log_artifact(filename, artifact_path="fresh_prediction_results")

    logger.info('Done.')


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
    Net, _ = import_modules(net_type=net_type)

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

        # calculate similarity scores
        similarity_scores = model.get_similarity(queries['embeddings'], embeddings)['similarity'].cpu().detach()

        # get ranks per query sample:
        # for each query sample -> order samples labels/shas based on the similarity measure
        # (skipping the query sample itself)
        rank_per_query.update({
            i: {
                'query_sha': s,
                'ground_truth_label': int(queries['labels'][i].item()),
                'ground_truth_family': label_to_sig(int(queries['labels'][i].item())),
                'rank_shas': np.asarray(shas, dtype=np.dtype('U64'))[similarity_scores[
                    i, [j for j in range(len(similarity_scores[i])) if shas[j] != s]].argsort()].tolist(),
                'rank_labels': [int(lab) for lab in labels[
                    similarity_scores[i, [j for j in range(len(similarity_scores[i])) if shas[j] != s]].argsort()]],
                'rank_families': [label_to_sig(int(lab.item()))
                                  for lab in labels[similarity_scores[
                        i, [j for j in range(len(similarity_scores[i])) if shas[j] != s]].argsort()]]
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
        mlflow.log_artifact(filename, 'fresh_ranking_results')

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
            mlflow.log_artifact(df_filename, 'fresh_ranking_results')

    logger.info('Done.')


@baker.command
def evaluate_fresh(ds_path,  # path of the directory where to find the fresh dataset (containing .dat files)
                   checkpoint_path,  # path to the model checkpoint to load
                   # network to use between 'JointEmbedding', 'JointEmbedding_cosine',
                   # 'JointEmbedding_pairwise_distance' and 'DetectionBase'
                   net_type='JointEmbedding',
                   n_anchor_samples_per_family=10,  # how many anchor samples to use in the family prediction task
                   # whether to perform a 'hard' (1) or 'soft' (0) malware family prediction
                   hard=0,
                   n_queries=100,  # number of queries to do in the family ranking task
                   batch_size=1000):  # how many samples per batch to load
    """ Evaluate the model on both the family prediction task and on the family ranking task.

    Args:
        ds_path: Path of the directory where to find the fresh dataset (containing .dat files)
        checkpoint_path: Path to the model checkpoint to load
        net_type: Network to use between 'JointEmbedding', 'JointEmbedding_cosine',
                    'JointEmbedding_pairwise_distance' and 'DetectionBase'  (default: 'JointEmbedding')
        n_anchor_samples_per_family: How many anchor samples to use in the family prediction task (default: 10)
        hard: Whether to perform a 'hard' (1) or 'soft' (0) malware family prediction (default: 0)
        n_queries: Number of queries to do in the family ranking task (default: 100)
        batch_size: How many samples per batch to load (default: 1000)
    """

    # start mlflow run
    with mlflow.start_run():
        logger.info('Now launching "evaluate_fresh_predictions" function..')
        # evaluate model on the family prediction task
        evaluate_fresh_predictions(ds_path=ds_path,
                                   checkpoint_path=checkpoint_path,
                                   net_type=net_type,
                                   n_anchor_samples_per_family=n_anchor_samples_per_family,
                                   hard=bool(hard),
                                   batch_size=batch_size)

        logger.info('Now launching "evaluate_fresh_rankings" function..')
        # evaluate model on the family ranking task
        evaluate_fresh_rankings(ds_path=ds_path,
                                checkpoint_path=checkpoint_path,
                                net_type=net_type,
                                n_queries=n_queries,
                                batch_size=batch_size)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
