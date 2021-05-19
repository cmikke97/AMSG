import configparser  # implements a basic configuration language for Python programs
import os  # Provides a portable way of using operating system dependent functionality
import re  # provides regular expression matching operations
import tempfile  # used to create temporary files and directories
from copy import deepcopy  # creates a new object and recursively copies the original object elements

import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np
import torch  # Tensor library like NumPy, with strong GPU support
import torch.nn.functional as F  # pytorch neural network functional interface
from torch import nn  # a neural networks library deeply integrated with autograd designed for maximum flexibility

from .dataset import Dataset

# get tags from the dataset
all_tags = Dataset.tags

# get config file path
utils_dir = os.path.dirname(os.path.abspath(__file__))
detection_base_dir = os.path.dirname(utils_dir)
src_dir = os.path.dirname(detection_base_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file
device = config['detectionBase']['device']


def compute_loss(predictions,  # a dictionary of results from a PENetwork model
                 labels,  # a dictionary of labels
                 loss_wts=None):  # weights to assign to each head of the network (if it exists)
    """ Compute losses for a malware feed-forward neural network (optionally with SMART tags and vendor detection count
    auxiliary losses).

    Args:
        predictions: a dictionary of results from a PENetwork model
        labels: a dictionary of labels
        loss_wts: weights to assign to each head of the network (if it exists); defaults to values used in the
                  ALOHA paper (1.0 for malware, 0.1 for count and each tag)
    Returns:
        Loss dictionary
    """

    # if no loss_wts were provided set some default values
    if loss_wts is None:
        loss_wts = {'malware': 1.0,
                    'count': 0.1,
                    'tags': 1.0}

    loss_dict = {'total': 0.}  # initialize dictionary of losses

    if 'malware' in labels:  # if the malware head is enabled
        # extract ground truth malware label, convert it to float and allocate it into the selected device (CPU or GPU)
        malware_labels = labels['malware'].float().to(device)

        # get predicted malware label, reshape it to the same shape of malware_labels
        # then calculate binary cross entropy loss with respect to the ground truth malware labels
        malware_loss = F.binary_cross_entropy(predictions['malware'].reshape(malware_labels.shape),
                                              malware_labels)

        # get loss weight (or set to default if not provided)
        weight = loss_wts['malware'] if 'malware' in loss_wts else 1.0

        # copy calculated malware loss into the loss dictionary
        loss_dict['malware'] = deepcopy(malware_loss.item())

        # update total loss
        loss_dict['total'] += malware_loss * weight

    if 'count' in labels:  # if the count head is enabled
        # extract ground truth count, convert it to float and allocate it into the selected device (CPU or GPU)
        count_labels = labels['count'].float().to(device)

        # get predicted count, reshape it to the same shape of count_labels
        # then calculate poisson loss with respect to the ground truth count
        count_loss = torch.nn.PoissonNLLLoss()(predictions['count'].reshape(count_labels.shape),
                                               count_labels)

        # get loss weight (or set to default if not provided)
        weight = loss_wts['count'] if 'count' in loss_wts else 1.0

        # copy calculated count loss into the loss dictionary
        loss_dict['count'] = deepcopy(count_loss.item())

        # update total loss
        loss_dict['total'] += count_loss * weight

    if 'tags' in labels:  # if the tags head is enabled
        # extract ground truth tags, convert them to float and allocate them into the selected device (CPU or GPU)
        tag_labels = labels['tags'].float().to(device)

        # get predicted tags and then calculate binary cross entropy loss with respect to the ground truth tags
        tags_loss = F.binary_cross_entropy(predictions['tags'],
                                           tag_labels)

        # get loss weight (or set to default if not provided)
        weight = loss_wts['tags'] if 'tags' in loss_wts else 1.0

        # copy calculated tags loss into the loss dictionary
        loss_dict['tags'] = deepcopy(tags_loss.item())

        # update total loss
        loss_dict['total'] += tags_loss * weight

    return loss_dict  # return the losses


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


def normalize_results(labels_dict,  # labels (ground truth) dictionary
                      results_dict,  # results (predicted labels) dictionary
                      use_malware=False,  # whether or not to use malware/benignware labels as a target
                      use_count=False,  # whether or not to use the counts as an additional target
                      use_tags=False):  # whether or not to use SMART tags as additional targets
    """ Take a set of results dicts and break them out into a single dict of 1d arrays with appropriate column names
    that pandas can convert to a DataFrame.

    Args:
        labels_dict: Labels (ground truth) dictionary
        results_dict: Results (predicted labels) dictionary
        use_malware: Whether or not to use malware/benignware labels as a target
        use_count: Whether or not to use the counts as an additional target
        use_tags: Whether or not to use SMART tags as additional targets
    Returns:
        Dictionary containing labels and predictions.
    """
    # a lot of deepcopies are done here to avoid a FD "leak" in the dataset generator
    # see here: https://github.com/pytorch/pytorch/issues/973#issuecomment-459398189

    rv = {}  # initialize return value dict

    if use_malware:  # if the malware/benign target label is enabled
        # normalize malware ground truth label array and save it into rv
        rv['label_malware'] = detach_and_copy_array(labels_dict['malware'])
        # normalize malware predicted label array and save it into rv
        rv['pred_malware'] = detach_and_copy_array(results_dict['malware'])

    if use_count:  # if the count additional target is enabled
        # normalize ground truth count array and save it into rv
        rv['label_count'] = detach_and_copy_array(labels_dict['count'])
        # normalize predicted count array and save it into rv
        rv['pred_count'] = detach_and_copy_array(results_dict['count'])

    if use_tags:  # if the SMART tags additional targets are enabled
        for column, tag in enumerate(all_tags):  # for all the tags
            # normalize ground truth tag array and save it into rv
            rv['label_{}_tag'.format(tag)] = detach_and_copy_array(labels_dict['tags'][:, column])
            # normalize predicted tag array and save it into rv
            rv['pred_{}_tag'.format(tag)] = detach_and_copy_array(results_dict['tags'][:, column])

    return rv


class Net(nn.Module):
    """ This is a simple network loosely based on the one used in ALOHA: Auxiliary Loss Optimization for Hypothesis
    Augmentation (https://arxiv.org/abs/1903.05700). Note that it uses fewer (and smaller) layers, as well as a single
    layer for all tag predictions, performance will suffer accordingly.
    """

    def __init__(self,
                 use_malware=True,  # whether to use the malicious label for the data points or not
                 use_counts=True,  # whether to use the counts for the data points or not
                 use_tags=True,  # whether to use the tags for the data points or not
                 n_tags=None,  # number of tags to predict
                 feature_dimension=2381,  # dimension of the input data feature vector
                 layer_sizes=None):  # layer sizes (array of sizes)
        """ Initialize net.

        Args:
            use_malware: Whether to use the malicious label for the data points or not
            use_counts: Whether to use the counts for the data points or not
            n_tags: Number of tags to predict
            feature_dimension: Dimension of the input data feature vector
            layer_sizes: Layer sizes (array of sizes)
        """

        # set some attributes
        self.use_malware = use_malware
        self.use_counts = use_counts
        self.use_tags = use_tags
        self.n_tags = n_tags

        if self.use_tags and self.n_tags is None:  # if we set to use tags but n_tags was None raise an exception
            raise ValueError("n_tags was None but we're trying to predict tags. Please include n_tags")

        super().__init__()  # call __init__() method of nn.Module

        # set dropout probability
        p = 0.05

        layers = []  # initialize layers array

        # if layer_sizes was not defined (it is None) then initialize it to a default of [512, 512, 128]
        if layer_sizes is None:
            layer_sizes = [512, 512, 128]

        # for each layer size in layer_sizes
        for i, ls in enumerate(layer_sizes):
            if i == 0:
                # append the first Linear Layer with dimensions feature_dimension x ls
                layers.append(nn.Linear(feature_dimension, ls))
            else:
                # append a Linear Layer with dimensions layer_sizes[i-1] x ls
                layers.append(nn.Linear(layer_sizes[i - 1], ls))

            layers.append(nn.LayerNorm(ls))  # append a Norm layer of size ls
            layers.append(nn.ELU())  # append an ELU activation function module
            layers.append(nn.Dropout(p))  # append a dropout layer with probability of dropout p

        # create a tuple from the layers list, then apply nn.Sequential to get a sequential container
        # -> this will be the model base
        self.model_base = nn.Sequential(*tuple(layers))

        # create malware/benign labeling head
        self.malware_head = nn.Sequential(nn.Linear(layer_sizes[-1], 1),
                                          # append a Linear Layer with size layer_sizes[-1] x 1
                                          nn.Sigmoid())  # append a sigmoid activation function module

        # create count poisson regression head
        self.count_head = nn.Linear(layer_sizes[-1], 1)  # append a Linear Layer with size layer_sizes[-1] x 1

        # sigmoid activation function
        self.sigmoid = nn.Sigmoid()

        # create a tag multi-label classifying head
        self.tag_head = nn.Sequential(nn.Linear(layer_sizes[-1], 64),
                                      # append a Linear Layer with size layer_sizes[-1] x 64
                                      nn.ELU(),  # append an ELU activation function module
                                      nn.Linear(64, 64),  # append a Linear Layer with size 64 x 64
                                      nn.ELU(),  # append an ELU activation function module
                                      nn.Linear(64, n_tags),  # append a Linear Layer with size 64 x n_tags
                                      nn.Sigmoid())  # append a sigmoid activation function module

    def forward(self,
                data):  # current batch of data (features)
        """ Forward batch of data through the net.

        Args:
            data: Current batch of data (features)
        Returns:
            Dictionary containing predicted labels.
        """

        rv = {}  # initialize return value

        # get base result forwarding the data through the base model
        base_result = self.model_base.forward(data)

        if self.use_malware:
            rv['malware'] = self.malware_head(base_result)  # append to return value the result of the malware head

        if self.use_counts:
            rv['count'] = self.count_head(base_result)  # append to return value the result of the count head

        if self.use_tags:
            rv['tags'] = self.tag_head(base_result)  # append to return value the result of the tag head

        return rv  # return the return value

    def save(self,
             epoch):  # current epoch
        """ Saves model state dictionary to temp directory and then logs it.

        Args:
            epoch: Current epoch
        """

        # create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # compute filename
            filename = os.path.join(temp_dir, "epoch_{}.pt".format(str(epoch)))

            # save model state of the current epoch to temp dir
            torch.save(self.state_dict(), filename)

            # log checkpoint file as artifact
            mlflow.log_artifact(filename, artifact_path="model_checkpoints")

    def load(self,
             path):  # path where to (try) retrieve model checkpoint from
        """ Loads model checkpoint from current run artifacts, if it exists.

        Args:
            path: Path where to (try) retrieve model checkpoint from
        Returns:
            Next epoch number.
        """

        # initialize last epoch done to 0
        last_epoch_done = 0
        # if the checkpoint directory exists
        if os.path.exists(path):
            # get the latest checkpoint epoch saved in checkpoint dir
            last_epoch_done = self.last_epoch_done(path)
            # if it is not none, load model state of the specified epoch from checkpoint dir
            if last_epoch_done is not None:
                self.load_state_dict(torch.load(os.path.join(path, "epoch_{}.pt".format(str(last_epoch_done)))))
            else:
                # otherwise just set last_epoch_done to 0
                last_epoch_done = 0

        # return next epoch to be done
        return last_epoch_done + 1

    @staticmethod
    def last_epoch_done(checkpoint_dir):  # path where to search the model state
        """ Get last epoch completed by previous run.

        Args:
            checkpoint_dir: Path where to search the model state
        Returns:
            Epoch of the latest checkpoint if there are checkpoints in the directory provided, otherwise 'None'
        """

        # set current highest epoch value
        max_epoch = None
        # get highest epoch from the model checkpoints present in the directory
        for epoch in {re.match(r'.*epoch_(\d+).pt', filename).group(1) for filename in os.listdir(checkpoint_dir)}:
            if max_epoch is None or epoch > max_epoch:
                max_epoch = epoch

        # return current highest epoch
        return max_epoch