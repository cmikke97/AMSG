import configparser  # implements a basic configuration language for Python programs
import os  # provides a portable way of using operating system dependent functionality
from copy import deepcopy  # creates a new object and recursively copies the original object elements

import torch  # tensor library like NumPy, with strong GPU support
import torch.nn.functional as F  # pytorch neural network functional interface
from torch import nn  # a neural networks library deeply integrated with autograd designed for maximum flexibility

from .generators.dataset import Dataset
from .utils.Net import Net as baseNet

# get tags from the dataset
all_tags = Dataset.tags

# get config file path
nets_dir = os.path.dirname(os.path.abspath(__file__))
model_dir = os.path.dirname(nets_dir)
src_dir = os.path.dirname(model_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file
device = config['detectionBase']['device']


class Net(baseNet):
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
                 layer_sizes=None,  # layer sizes (array of sizes)
                 dropout_p=0.05,  # dropout probability
                 activation_function='elu'):  # non-linear activation function
        """ Initialize net.

        Args:
            use_malware: Whether to use the malicious label for the data points or not
            use_counts: Whether to use the counts for the data points or not
            use_tags: Whether to use the SMART tags for the data points or not
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

        super().__init__()

        layers = []  # initialize layers array

        # if layer_sizes was not defined (it is None) then initialize it to a default of [512, 512, 128]
        if layer_sizes is None:
            layer_sizes = [512, 512, 128]

        if activation_function.lower() == 'elu':
            self.activation_function = nn.ELU
        elif activation_function.lower() == 'leakyRelu':
            self.activation_function = nn.LeakyReLU
        elif activation_function.lower() == 'pRelu':
            self.activation_function = nn.PReLU
        elif activation_function.lower() == 'relu':
            self.activation_function = nn.ReLU
        else:
            raise ValueError('Unknown activation function {}. Try "elu", "leakyRelu", "pRelu" or "relu"'
                             .format(activation_function))

        # for each layer size in layer_sizes
        for i, ls in enumerate(layer_sizes):
            if i == 0:
                # append the first Linear Layer with dimensions feature_dimension x ls
                layers.append(nn.Linear(feature_dimension, ls))
            else:
                # append a Linear Layer with dimensions layer_sizes[i-1] x ls
                layers.append(nn.Linear(layer_sizes[i - 1], ls))

            layers.append(nn.LayerNorm(ls))  # append a Norm layer of size ls
            layers.append(self.activation_function())  # append an ELU activation function module
            layers.append(nn.Dropout(dropout_p))  # append a dropout layer with probability of dropout dropout_p

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

    @staticmethod
    def compute_loss(predictions,  # a dictionary of results from a PENetwork model
                     labels,  # a dictionary of labels
                     loss_wts=None):  # weights to assign to each head of the network (if it exists)
        """ Compute losses for a malware feed-forward neural network (optionally with SMART tags and vendor detection
        count auxiliary losses).

        Args:
            predictions: A dictionary of results from a PENetwork model
            labels: A dictionary of labels
            loss_wts: Weights to assign to each head of the network (if it exists); defaults to values used in the
                      ALOHA paper (1.0 for malware, 0.1 for count and each tag)
        Returns:
            Loss dictionary.
        """

        # if no loss_wts were provided set some default values
        if loss_wts is None:
            loss_wts = {'malware': 1.0,
                        'count': 0.1,
                        'tags': 1.0}

        loss_dict = {'total': 0.}  # initialize dictionary of losses

        if 'malware' in labels:  # if the malware head is enabled
            # extract ground truth malware label, convert it to float and allocate it into the selected device
            # (CPU or GPU)
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

    @staticmethod
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
            use_malware: Whether to use malware/benignware labels as a target
            use_count: Whether to use the counts as an additional target
            use_tags: Whether to use SMART tags as additional targets
        Returns:
            Dictionary containing labels and predictions.
        """

        # a lot of deepcopies are done here to avoid a FD "leak" in the dataset generator
        # see here: https://github.com/pytorch/pytorch/issues/973#issuecomment-459398189

        rv = {}  # initialize return value dict

        if use_malware:  # if the malware/benign target label is enabled
            # normalize malware ground truth label array and save it into rv
            rv['label_malware'] = baseNet.detach_and_copy_array(labels_dict['malware'])
            # normalize malware predicted label array and save it into rv
            rv['pred_malware'] = baseNet.detach_and_copy_array(results_dict['malware'])

        if use_count:  # if the count additional target is enabled
            # normalize ground truth count array and save it into rv
            rv['label_count'] = baseNet.detach_and_copy_array(labels_dict['count'])
            # normalize predicted count array and save it into rv
            rv['pred_count'] = baseNet.detach_and_copy_array(results_dict['count'])

        if use_tags:  # if the SMART tags additional targets are enabled
            for column, tag in enumerate(all_tags):  # for all the tags
                # normalize ground truth tag array and save it into rv
                rv['label_{}_tag'.format(tag)] = baseNet.detach_and_copy_array(labels_dict['tags'][:, column])
                # normalize predicted tag array and save it into rv
                rv['pred_{}_tag'.format(tag)] = baseNet.detach_and_copy_array(results_dict['tags'][:, column])

        return rv
