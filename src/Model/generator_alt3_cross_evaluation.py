import configparser  # implements a basic configuration language for Python programs
import importlib  # provides the implementation of the import statement in Python source code
import os  # provides a portable way of using operating system dependent functionality
import shutil  # used to recursively copy an entire directory tree rooted at src to a directory named dst
import sys  # system-specific parameters and functions
from collections import defaultdict  # dict subclass that calls a factory function to supply missing values
from copy import deepcopy  # creates a new object and recursively copies the original object elements
from urllib import parse  # standard interface to break Uniform Resource Locator (URL) in components
import time
from tqdm.auto import tqdm

import baker  # easy, powerful access to Python functions from the command line
import numpy as np  # the fundamental package for scientific computing with Python
import psutil
import torch  # tensor library like NumPy, with strong GPU support
from logzero import logger  # robust and effective logging for Python
from nets.generators.dataset_alt import Dataset
from nets.generators.generators_alt3 import get_generator


def import_modules(net_type):  # network type (possible values: jointEmbedding, detectionBase)
    """ Dynamically import network module depending on the provided argument.

    Args:
        net_type: Network type (possible values: jointEmbedding, detectionBase)
    Returns:
        Net, compute_loss and device imported from selected modules.
    """

    # set network module name based on the current network type
    if net_type.lower() == 'jointembedding':
        net_type = 'jointEmbedding'
        net_module_name = "nets.JointEmbedding_net"
    elif net_type.lower() == 'detectionbase':
        net_type = 'detectionBase'
        net_module_name = "nets.DetectionBase_net"
    else:  # if the network type is neither JointEmbedding nor DetectionBase raise ValueError
        raise ValueError('Unknown Network type. Possible values: "JointEmbedding", "DetectionBase". Got {}'
                         .format(net_type))

    # import net module
    net_module = importlib.import_module(net_module_name)
    # get 'Net' class from net module
    Net = getattr(net_module, 'Net')
    # get 'compute_loss' function from net module
    compute_loss = getattr(net_module, 'compute_loss')

    # get config file path
    model_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.dirname(model_dir)
    config_filepath = os.path.join(src_dir, 'config.ini')

    # instantiate config parser and read config file
    config = configparser.ConfigParser()
    config.read(config_filepath)

    # get variables from config file (the section depends on the net type)
    device = config[net_type]['device']

    # return classes, functions and variables imported
    return Net, compute_loss, device


@baker.command
def generator_alt3_cross_evaluation(ds_path: str,  # path of the directory where to find the pre-processed dataset (containing .dat files)
                                    net_type: str = 'JointEmbedding',  # network to use between 'JointEmbedding' and 'DetectionBase'
                                    batch_size: int = 8192,  # how many samples per batch to load
                                    min_chunk_size_exponent: int = 4,
                                    max_chunk_size_exponent: int = 14,
                                    min_chunks_exponent: int = 3,
                                    max_chunks_exponent: int = 13,
                                    epochs: int = 1,
                                    training_n_samples: int = -1,  # number of training samples to consider (used to access the right files)
                                    validation_n_samples: int = -1,  # number of validation samples to consider (used to access the right files)
                                    use_malicious_labels: int = 1,  # whether or not to use malware/benignware labels as a target
                                    use_count_labels: int = 1,  # whether or not to use the counts as an additional target
                                    use_tag_labels: int = 1,  # whether or not to use the tags as additional targets
                                    feature_dimension: int = 2381,  # The input dimension of the model
                                    # if provided, seed random number generation with this value (defaults None, no seeding)
                                    random_seed=None,
                                    # How many worker processes should the dataloader use (if None use multiprocessing.cpu_count())
                                    workers: int = None):
    """ Train a feed-forward neural network on EMBER 2.0 features, optionally with additional targets as described in
    the ALOHA paper (https://arxiv.org/abs/1903.05700). SMART tags based on (https://arxiv.org/abs/1905.06262).

    Args:
        ds_path: Path of the directory where to find the pre-processed dataset (containing .dat files).
        net_type: Network to use between 'JointEmbedding' and 'DetectionBase'. (default: 'JointEmbedding')
        gen_type: Generator (and dataset) class to use between 'base', 'alt1', 'alt2'. (default: 'base')
        run_id: Mlflow run id of a previously stopped run to resume.
        training_run: Training run identifier. (default: 0) -> to plot base evaluation results with mean and confidence
                      we need at least 2 runs
        batch_size: How many samples per batch to load. (default: 8192)
        epochs: How many epochs to train for. (default: 1)
        training_n_samples: Number of training samples to consider (used to access the right files).
                            (default: -1 -> all)
        validation_n_samples: Number of validation samples to consider (used to access the right files).
                              (default: -1 -> all)
        use_malicious_labels: Whether or (1/0) not to use malware/benignware labels as a target. (default: 1)
        use_count_labels: Whether or not (1/0) to use the counts as an additional target. (default: 1)
        use_tag_labels: Whether or not (1/0) to use the tags as additional targets. (default: 1)
        feature_dimension: The input dimension of the model. (default: 2381 -> EMBER 2.0 feature size)
        random_seed: If provided, seed random number generation with this value. (default: None -> no seeding)
        workers: How many worker processes should the dataloader use (default: None -> use multiprocessing.cpu_count())
    """

    # dynamically import some classes, functions and variables from modules depending on the current net and gen types
    Net, compute_loss, device = import_modules(net_type=net_type)

    if net_type == 'JointEmbedding':
        use_tag_labels = 1

    # if workers has a value (it is not None) then convert it to int
    workers = workers if workers is None else int(workers)

    if random_seed is not None:  # if a seed was provided
        logger.info(f"Setting random seed to {int(random_seed)}.")
        # set the seed for generating random numbers
        torch.manual_seed(int(random_seed))

    logger.info('Running generator alternative 3 cross evaluation..')

    chunk_size_iterator = [2 ** x for x in range(min_chunk_size_exponent, max_chunk_size_exponent + 1)]
    chunks_iterator = [2 ** x for x in range(min_chunks_exponent, max_chunks_exponent + 1)]

    for chunk_size in chunk_size_iterator:
        for chunks in chunks_iterator:

            # create malware-NN model
            model = Net(use_malware=bool(use_malicious_labels),
                        use_counts=bool(use_count_labels),
                        use_tags=bool(use_tag_labels),
                        n_tags=len(Dataset.tags),  # get n_tags counting tags from the dataset
                        feature_dimension=feature_dimension)

            # use Adam optimizer on all the model parameters
            opt = torch.optim.Adam(model.parameters())

            # create generator (a.k.a. Dataloader)
            generator = get_generator(ds_root=ds_path,
                                      batch_size=batch_size,
                                      chunk_size=chunk_size,
                                      chunks=chunks,
                                      mode='train',
                                      num_workers=workers,
                                      n_samples=training_n_samples,
                                      use_malicious_labels=bool(use_malicious_labels),
                                      use_count_labels=bool(use_count_labels),
                                      use_tag_labels=bool(use_tag_labels))

            # get number of steps per epoch (# of total batches) from generator
            steps_per_epoch = len(generator)

            # allocate model to selected device
            model.to(device)

            # instantiate a new dictionary-like object called loss_histories
            loss_histories = defaultdict(list)
            # set the model mode to 'train'
            model.train()

            for epoch in range(epochs):

                # set start time
                start_time = time.time()

                # for all the training batches
                for i, (features, labels) in enumerate(generator):
                    opt.zero_grad()  # clear old gradients from the last step

                    # copy current features and allocate them on the selected device (CPU or GPU)
                    features = deepcopy(features).to(device)

                    # perform a forward pass through the network
                    out = model(features)

                    # compute loss given the predicted output from the model
                    loss_dict = compute_loss(out, deepcopy(labels))  # copy the ground truth labels

                    # extract total loss
                    loss = loss_dict['total']

                    # compute gradients
                    loss.backward()

                    # update model parameters
                    opt.step()

                    # for all the calculated losses in loss_dict
                    for k in loss_dict.keys():
                        # if the loss is 'total' then append it to loss_histories['total'] after having detached it
                        # and passed it to the cpu
                        if k == 'total':
                            loss_histories[k].append(deepcopy(loss_dict[k].detach().cpu().item()))
                        # otherwise append the loss to loss_histories without having to detach it
                        else:
                            loss_histories[k].append(loss_dict[k])

                    # create loss string with the current losses
                    loss_str = " ".join([f"{key} loss:{value:7.3f}" for key, value in loss_dict.items()])
                    loss_str += " | "
                    loss_str += " ".join([f"{key} mean:{np.mean(value):7.3f}" for key, value in loss_histories.items()])
                    # additional info
                    loss_str += " || [RAM used: {}%, Time elapsed: {}]"\
                        .format(psutil.virtual_memory().percent,
                                time.strftime("%H:%M:%S", time.gmtime(time.time() - start_time)))
                    # write on standard out the loss string + other information
                    sys.stdout.write('\r Epoch: {}/{} {}/{} '.format(epoch, epochs, i + 1, steps_per_epoch) + loss_str)
                    # flush standard output
                    sys.stdout.flush()
                    del features, labels  # to avoid weird references that lead to generator errors

                    print()

    logger.info('...done')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
