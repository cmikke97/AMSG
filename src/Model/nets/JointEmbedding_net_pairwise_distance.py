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
device = config['general']['device']
sim_function = config['jointEmbedding']['pairwise_distance_to_similarity_function']
sim_function_a = float(config['jointEmbedding']['pairwise_a'])


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


class Net(baseNet):
    """ Joint Embedding Network which calculated embeddings similarity using the inverse of the pairwise distance. """

    def __init__(self,
                 use_malware=True,  # whether to use the malicious label for the data points or not
                 use_counts=True,  # whether to use the counts for the data points or not
                 use_tags=True,  # whether to use the tags for the data points or not
                 n_tags=None,  # number of tags to predict
                 feature_dimension=2381,  # dimension of the input data feature vector
                 embedding_dimension=32,  # joint latent space size
                 max_embedding_norm=1,  # value at which to constrain the embedding vector norm to
                 layer_sizes=None,  # layer sizes (array of sizes)
                 dropout_p=0.05,  # dropout probability
                 activation_function='elu',  # non-linear activation function to use
                 normalization_function='batch_norm'):  # normalization function to use
        """ Initialize net.

        Args:
            use_malware: Whether to use the malicious label for the data points or not
            use_counts: Whether to use the counts for the data points or not
            use_tags: Whether to use the tags for the data points or not. NOTE: this is here just for compatibility with
                      the training procedure. With the joint embedding network the tags will always be used, even if
                      this flag is false.
            n_tags: Number of tags to predict
            feature_dimension: Dimension of the input data feature vector
            embedding_dimension: Joint latent space size
            max_embedding_norm: Value at which to constrain the embedding vector norm to
            layer_sizes: Layer sizes (array of sizes)
            dropout_p: Dropout probability
            activation_function: Non-linear activation function to use (may be "elu", "leakyRelu", "pRelu" or "relu")
                (default: "elu")
            normalization_function: Normalization function to use (may be "layer_norm" or "batch_norm")
                (default: "batch_norm")
        """

        self.use_malware = use_malware
        self.use_counts = use_counts
        self.n_tags = n_tags
        self.embedding_dimension = embedding_dimension

        if self.n_tags is None:  # if we set to use tags but n_tags was None raise an exception
            raise ValueError("n_tags was None but we're trying to predict tags. Please include n_tags")

        # initialize super class
        super().__init__()

        layers = []  # initialize layers array

        # if layer_sizes was not defined (it is None) then initialize it to a default of [512, 512, 128]
        if layer_sizes is None:
            layer_sizes = [512, 512, 128]

        # select activation function to use based on the activation_function parameter
        if activation_function.lower() == 'elu':
            self.activation_function = nn.ELU
        elif activation_function.lower() == 'leakyrelu':
            self.activation_function = nn.LeakyReLU
        elif activation_function.lower() == 'prelu':
            self.activation_function = nn.PReLU
        elif activation_function.lower() == 'relu':
            self.activation_function = nn.ReLU
        else:  # if the provided function is not recognised, raise error
            raise ValueError('Unknown activation function {}. Try "elu", "leakyRelu", "pRelu" or "relu"'
                             .format(activation_function))

        # select normalization function to use based on the normalization_function parameter
        if normalization_function.lower() == 'layer_norm':
            self.normalization_function = nn.LayerNorm
        elif normalization_function.lower() == 'batch_norm':
            self.normalization_function = nn.BatchNorm1d
        else:  # if the provided normalization function is not recognised, raise error
            raise ValueError('Unknown activation function {}. Try "layer_norm" or "batch_norm"'
                             .format(activation_function))

        # for each layer size in layer_sizes
        for i, ls in enumerate(layer_sizes):
            if i == 0:
                # append the first Linear Layer with dimensions feature_dimension x ls
                layers.append(nn.Linear(feature_dimension, ls))
            else:
                # append a Linear Layer with dimensions layer_sizes[i-1] x ls
                layers.append(nn.Linear(layer_sizes[i - 1], ls))

            layers.append(self.normalization_function(ls))  # append a Norm layer of size ls
            layers.append(self.activation_function())  # append an ELU activation function module
            layers.append(nn.Dropout(dropout_p))  # append a dropout layer with probability of dropout dropout_p

        # create a tuple from the layers list, then apply nn.Sequential to get a sequential container
        # -> this will be the model base
        self.model_base = nn.Sequential(*tuple(layers))

        # create pe embedding head
        self.pe_embedding = nn.Sequential(nn.Linear(layer_sizes[-1], self.embedding_dimension),
                                          self.normalization_function(self.embedding_dimension),
                                          self.activation_function())

        # create malware/benign labeling head
        self.malware_head = nn.Sequential(nn.Linear(layer_sizes[-1], 1),
                                          # append a Linear Layer with size layer_sizes[-1] x 1
                                          nn.Sigmoid())  # append a sigmoid activation function module

        # # create count poisson regression head
        # self.count_head = nn.Linear(layer_sizes[-1], 1)  # append a Linear Layer with size layer_sizes[-1] x 1

        # create count poisson regression head
        self.count_head = nn.Sequential(nn.Linear(layer_sizes[-1], 1),
                                        # append a Linear Layer with size layer_sizes[-1] x 1
                                        nn.ReLU())  # append a Relu activation function module

        # sigmoid activation function
        self.sigmoid = nn.Sigmoid()

        # create tag embedding
        self.tags_embedding = nn.Embedding(self.n_tags,  # number of lines of the embedding
                                           self.embedding_dimension,  # dimension of each embedding line
                                           max_norm=max_embedding_norm)  # constrain the embedding vector norm

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
        base_out = self.model_base(data)

        if self.use_malware:
            rv['malware'] = self.malware_head(base_out)  # append to return value the result of the malware head

        if self.use_counts:
            rv['count'] = self.count_head(base_out)  # append to return value the result of the count head

        # get PE embedding
        pe_embedding = self.pe_embedding.forward(base_out)

        # get tags embedding
        tags_embedding = self.tags_embedding(torch.LongTensor(Dataset.encoded_tags).to(device))

        # calculate distances between PE and tags embeddings
        distances = torch.cdist(pe_embedding, tags_embedding, p=2.0)

        # calculate similarity score calculating the inverse of the distances
        similarity_scores = distance_to_similarity(distances,
                                                   a=sim_function_a,
                                                   function=sim_function)

        # save similarity score in result dictionary
        rv['similarity'] = similarity_scores

        # save probability score in result dictionary
        rv['probability'] = similarity_scores

        return rv  # return return value

    def get_embedding(self,
                      data):  # current batch of data (features)
        """ Forward batch of data through the net and get resulting embedding.

        Args:
            data: Current batch of data (features)
        Returns:
            Dictionary containing the resulting embedding.
        """

        rv = {}  # initialize return value

        # get base result forwarding the data through the base model
        base_out = self.model_base(data)

        # get PE embedding
        pe_embedding = self.pe_embedding.forward(base_out)

        # save embedding score in result dictionary
        rv['embedding'] = pe_embedding

        return rv  # return the return value

    def get_similarity(self,
                       first_embedding,  # embeddings of a batch of data (dim: batch_dim_1 x 32)
                       second_embedding):  # embeddings of a batch of data (dim: batch_dim_2 x 32)
        """ Get similarity scores between two embedding matrices (embeddings of batches of data).

        Args:
            first_embedding: Embeddings of a batch of data (dim: batch_dim_1 x 32)
            second_embedding: Embeddings of a batch of data (dim: batch_dim_2 x 32)
        Returns:
              Similarity matrix (dim: batch_dim_1 x batch_dim_2).
        """

        # calculate distances between PE and tags embeddings
        distances = torch.cdist(first_embedding, second_embedding, p=2.0)

        # calculate similarity score calculating the inverse of the distances
        similarity_scores = distance_to_similarity(distances,
                                                   a=self.embedding_dimension,
                                                   function=sim_function)

        # save similarity and probability scores in result dictionary
        rv = {'similarity': similarity_scores, 'probability': similarity_scores}

        # return result dictionary
        return rv

    @staticmethod
    def compute_loss(predictions,  # a dictionary of results from the Net
                     labels,  # a dictionary of labels
                     loss_wts=None):  # weights to assign to each head of the network (if it exists)
        """ Compute Net losses (optionally with SMART tags and vendor detection count auxiliary losses).

        Args:
            predictions: A dictionary of results from the Net
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

        if 'tags' in labels:  # if the tags (Joint Embedding) head is enabled
            # extract ground truth tags, convert them to float and allocate them into the selected device (CPU or GPU)
            tag_labels = labels['tags'].float().to(device)

            # get similarity score from model prediction
            similarity_score = predictions['similarity']

            # calculate similarity loss
            similarity_loss = F.binary_cross_entropy(similarity_score,
                                                     tag_labels,
                                                     reduction='none').sum(dim=1).mean(dim=0)

            # get loss weight (or set to default if not provided)
            weight = loss_wts['tags'] if 'tags' in loss_wts else 1.0

            # copy calculated tags loss into the loss dictionary
            loss_dict['jointEmbedding'] = deepcopy(similarity_loss.item())

            # update total loss
            loss_dict['total'] += similarity_loss * weight

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
            use_tags: Whether to use SMART tags as additional targets. NOTE: this is here just for compatibility with
                      the evaluation procedure. With the joint embedding network the tags will always be used, even if
                      this flag is false.
        Returns:
            Dictionary containing labels and predictions.
        """

        # a lot of deepcopies are done here to avoid a FD "leak" in the dataset generator
        # see here: https://github.com/pytorch/pytorch/issues/973#issuecomment-459398189

        rv = {}  # initialize return value dict

        if use_malware:  # if the malware/benign target label is enabled
            # normalize malware ground truth label array and save it into rv
            rv['label_malware'] = Net.detach_and_copy_array(labels_dict['malware'])
            # normalize malware predicted label array and save it into rv
            rv['pred_malware'] = Net.detach_and_copy_array(results_dict['malware'])

        if use_count:  # if the count additional target is enabled
            # normalize ground truth count array and save it into rv
            rv['label_count'] = Net.detach_and_copy_array(labels_dict['count'])
            # normalize predicted count array and save it into rv
            rv['pred_count'] = Net.detach_and_copy_array(results_dict['count'])

        for column, tag in enumerate(all_tags):  # for all the tags
            # normalize ground truth tag array and save it into rv
            rv['label_{}_tag'.format(tag)] = Net.detach_and_copy_array(labels_dict['tags'][:, column])
            # normalize predicted tag array and save it into rv
            rv['pred_{}_tag'.format(tag)] = Net.detach_and_copy_array(results_dict['probability'][:, column])

        return rv
