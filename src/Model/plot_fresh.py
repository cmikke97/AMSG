import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import tempfile  # used to create temporary files and directories

import baker  # easy, powerful access to Python functions from the command line
import matplotlib  # comprehensive library for creating static, animated, and interactive visualizations in Python
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import torch
from numpy import interp
from sklearn.metrics import auc
from sklearn.metrics import confusion_matrix
from sklearn.preprocessing import label_binarize

from nets.generators.fresh_generators import get_generator
from utils.plot_utils import *

SMALL_SIZE = 18
MEDIUM_SIZE = 20
BIGGER_SIZE = 22

plt.rc('font', size=MEDIUM_SIZE)  # controls default text sizes
plt.rc('axes', titlesize=MEDIUM_SIZE)  # fontsize of the axes title
plt.rc('axes', labelsize=MEDIUM_SIZE)  # fontsize of the x and y labels
plt.rc('xtick', labelsize=MEDIUM_SIZE)  # fontsize of the tick labels
plt.rc('ytick', labelsize=MEDIUM_SIZE)  # fontsize of the tick labels
plt.rc('legend', fontsize=MEDIUM_SIZE)  # legend fontsize
plt.rc('figure', titlesize=BIGGER_SIZE)  # fontsize of the figure title

matplotlib.use('Agg')  # Select 'Agg' as the backend used for rendering and GUI integration

# define default family colors to be used in the graph
default_family_colors = ['r', 'r', 'r',
                         'g', 'g', 'b',
                         'b', 'm', 'm',
                         'c']

# define default family linestyles to be used in the graph
default_family_linestyles = [':', '--', '-.',
                             ':', '--', ':',
                             '--', ':', '--',
                             ':']

score_functions = {
    'accuracy': accuracy_score,
    'precision': precision_score,
    'recall': recall_score,
    'f1_score': f1_score,
    'confusion_matrix': confusion_matrix
}


def plot_score_trend(values_dict,
                     filename,
                     key,
                     style,
                     std_alpha=.2):
    # if the style was not defined (it is None)
    if style is None:
        raise ValueError('No default style information is available for f-way {} score;'
                         ' please provide (linestyle, color)'.format(key))
    else:  # otherwise (the style was defined)
        color, linestyle = style  # get linestyle and color from style

    x = np.array([k for k in values_dict.keys()])
    y_mean = np.array([v['mean'] for v in values_dict.values()])
    y_std = np.array([v['std'] for v in values_dict.values()])

    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))

    plt.plot(x, y_mean, color + linestyle, linewidth=2.0)

    # fill uncertainty area around ROC curve
    plt.fill_between(x,
                     y_mean - y_std,
                     y_mean + y_std,
                     color=color,
                     alpha=std_alpha)

    plt.ylabel(key)  # set the label for the y-axis
    plt.xlabel('number of anchors')  # set the label for the x-axis
    plt.title("f-way {} results".format(key))  # set plot title
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure
    plt.close()


def plot_confusion_matrix(cm,
                          filename,
                          n_anchors,
                          families):
    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))
    # fig, ax = plt.subplots()
    im = plt.imshow(cm)

    threshold = im.norm(cm.max()) / 2
    textcolors = ("white", "black")

    plt.xticks(np.arange(len(families)), families, rotation=45, ha="right", rotation_mode="anchor")
    plt.yticks(np.arange(len(families)), families)

    plt.xlabel('predicted')
    plt.ylabel('ground truth')

    # Loop over data dimensions and create text annotations.
    for i in range(len(families)):
        for j in range(len(families)):
            plt.text(j, i, cm[i, j], ha="center", va="center", color=textcolors[int(im.norm(cm[i, j]) > threshold)])

    plt.title("Confusion matrix with {} anchors".format(n_anchors))
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure
    plt.close()


def compute_fresh_scores(predictions_json_path):
    with open(predictions_json_path, 'r') as infile:
        predictions = json.load(infile)

    families = None
    scores = {
        'precision': {'macro': {}, 'micro': {}},
        'recall': {'macro': {}, 'micro': {}},
        'f1_score': {'macro': {}, 'micro': {}},
    }
    accuracies = {}
    confusion_matrixes = {}

    min_n_anchors = np.min([int(n) for n in predictions.keys()])

    for n_anchors in predictions.keys():
        if families is None:
            families = predictions[n_anchors][0]['families']

        curr_accuracy = []
        curr_scores = {
            'precision': {'macro': [], 'micro': []},
            'recall': {'macro': [], 'micro': []},
            'f1_score': {'macro': [], 'micro': []},
        }
        curr_confusion_matrix = []

        for curr_preds in predictions[n_anchors]:
            curr_accuracy.append(score_functions['accuracy'](curr_preds['labels'], curr_preds['predictions']))
            curr_confusion_matrix.append(score_functions['confusion_matrix'](curr_preds['labels'],
                                                                             curr_preds['predictions']))

            for key, val in curr_scores.items():
                curr_scores[key]['macro'].append(score_functions[key](curr_preds['labels'],
                                                                      curr_preds['predictions'],
                                                                      average='macro',
                                                                      zero_division=0))
                curr_scores[key]['micro'].append(score_functions[key](curr_preds['labels'],
                                                                      curr_preds['predictions'],
                                                                      average='micro',
                                                                      zero_division=0))

        accuracies[n_anchors] = {
            'mean': float(np.mean(curr_accuracy, dtype=np.float32)),
            'std': float(np.std(curr_accuracy, dtype=np.float32))
        }
        mlflow.log_metric('mean_accuracy',
                          float(np.mean(curr_accuracy, dtype=np.float32)),
                          int(n_anchors))

        confusion_matrixes[n_anchors] = {
            'max': curr_confusion_matrix[torch.argmax(torch.tensor(curr_accuracy))],
            'min': curr_confusion_matrix[torch.argmin(torch.tensor(curr_accuracy))]
        }
        for key, val in curr_scores.items():
            scores[key]['macro'][n_anchors] = {
                'mean': float(np.mean(curr_scores[key]['macro'], dtype=np.float32)),
                'std': float(np.std(curr_scores[key]['macro'], dtype=np.float32))
            }
            mlflow.log_metric('mean_{}'.format(key),
                              float(np.mean(curr_scores[key]['macro'], dtype=np.float32)),
                              int(n_anchors))

            scores[key]['micro'][n_anchors] = {
                'mean': float(np.mean(curr_scores[key]['micro'], dtype=np.float32)),
                'std': float(np.std(curr_scores[key]['micro'], dtype=np.float32))
            }
            mlflow.log_metric('mean_{}'.format(key),
                              float(np.mean(curr_scores[key]['micro'], dtype=np.float32)),
                              int(n_anchors))

    with tempfile.TemporaryDirectory() as tmpdir:
        acc_filename = os.path.join(tmpdir, 'accuracy.png')
        plot_score_trend(accuracies, filename=acc_filename, key='accuracy', style=('k', '-'))
        mlflow.log_artifact(acc_filename, 'fresh_scores_plots')

        for key, val in scores.items():
            filename_macro = os.path.join(tmpdir, '{}_macro.png'.format(key))
            filename_micro = os.path.join(tmpdir, '{}_micro.png'.format(key))

            plot_score_trend(val['macro'], filename=filename_macro, key=key, style=('k', '-'))
            plot_score_trend(val['micro'], filename=filename_micro, key=key, style=('k', '-'))

            mlflow.log_artifact(filename_macro, 'fresh_scores_plots')
            mlflow.log_artifact(filename_micro, 'fresh_scores_plots')

        max_mean_accuracy_n_anchors = torch.argmax(
            torch.tensor([a['mean'] for a in accuracies.values()])).item() + min_n_anchors
        cm_max_filename = os.path.join(tmpdir, 'conf_matrix_max_acc_anchors_{}.png'.format(max_mean_accuracy_n_anchors))
        cm_min_filename = os.path.join(tmpdir, 'conf_matrix_min_acc_anchors_{}.png'.format(max_mean_accuracy_n_anchors))

        plot_confusion_matrix(confusion_matrixes[str(max_mean_accuracy_n_anchors)]['max'],
                              filename=cm_max_filename,
                              n_anchors=max_mean_accuracy_n_anchors,
                              families=families)
        plot_confusion_matrix(confusion_matrixes[str(max_mean_accuracy_n_anchors)]['min'],
                              filename=cm_min_filename,
                              n_anchors=max_mean_accuracy_n_anchors,
                              families=families)

        mlflow.log_artifact(cm_max_filename, 'fresh_scores_plots')
        mlflow.log_artifact(cm_min_filename, 'fresh_scores_plots')


def get_mean_tprs(fpr_values,
                  tpr_values):
    all_fpr = np.unique(np.concatenate([fpr for fpr in fpr_values]))
    # Then interpolate all ROC curves at this points
    mean_tpr = np.zeros_like(all_fpr)
    for j in range(len(fpr_values)):
        mean_tpr += interp(all_fpr, fpr_values[j], tpr_values[j])
    # Finally average it and compute AUC
    mean_tpr /= len(fpr_values)

    return all_fpr, mean_tpr


def plot_fresh_results(predictions_json_path):
    with open(predictions_json_path, 'r') as infile:
        predictions = json.load(infile)

    values = {
        'roc_auc': {
            'macro': {},
            'micro': {}
        },
        # 'roc': {
        #     'macro': {},
        #     'micro': {}
        # }
    }
    families = None
    for n_anchors in predictions.keys():
        if families is None:
            families = predictions[n_anchors][0]['families']

            for key in families:
                values['roc_auc'][key] = {}
                # values['roc'][key] = {}

        curr_values = {
            # 'fpr': {'micro': [], 'macro': []},
            # 'tpr': {'micro': [], 'macro': []},
            'roc_auc': {'micro': [], 'macro': []}
        }
        # curr_values['fpr'].update({key: [] for key in families})
        # curr_values['tpr'].update({key: [] for key in families})
        curr_values['roc_auc'].update({key: [] for key in families})

        for curr_preds in predictions[n_anchors]:

            binarized_labels = label_binarize(curr_preds['labels'], classes=range(len(families)))

            fpr = {}
            tpr = {}
            roc_auc = {}
            for i, fam in enumerate(families):
                fpr[fam], tpr[fam], _ = roc_curve(binarized_labels[:, i],
                                                  torch.tensor(curr_preds['probabilities'])[:, i])
                roc_auc[fam] = auc(fpr[fam], tpr[fam])

                # curr_values['fpr'][str(fam)].append(fpr[fam])
                # curr_values['tpr'][str(fam)].append(tpr[fam])
                curr_values['roc_auc'][str(fam)].append(roc_auc[fam])

            # Compute micro-average ROC curve and ROC area
            fpr['micro'], tpr["micro"], _ = roc_curve(binarized_labels.ravel(),
                                                      torch.tensor(curr_preds['probabilities']).ravel())
            roc_auc['micro'] = auc(fpr["micro"], tpr["micro"])

            # curr_values['fpr']['micro'].append(fpr['micro'])
            # curr_values['tpr']['micro'].append(tpr['micro'])
            curr_values['roc_auc']['micro'].append(roc_auc['micro'])

            all_fpr = np.unique(np.concatenate([fpr[fam] for fam in families]))

            # Then interpolate all ROC curves at this points
            mean_tpr = np.zeros_like(all_fpr)
            for fam in families:
                mean_tpr += interp(all_fpr, fpr[fam], tpr[fam])

            # Finally average it and compute AUC
            mean_tpr /= len(families)

            fpr["macro"] = all_fpr
            tpr["macro"] = mean_tpr
            roc_auc["macro"] = auc(fpr["macro"], tpr["macro"])

            # curr_values['fpr']['macro'].append(fpr['macro'])
            # curr_values['tpr']['macro'].append(tpr['macro'])
            curr_values['roc_auc']['macro'].append(roc_auc['macro'])

        values['roc_auc']['macro'][n_anchors] = {
            'mean': float(np.mean(curr_values['roc_auc']['macro'], dtype=np.float32)),
            'std': float(np.std(curr_values['roc_auc']['macro'], dtype=np.float32))
        }
        mlflow.log_metric('mean_roc_auc_macro',
                          float(np.mean(curr_values['roc_auc']['macro'], dtype=np.float32)),
                          int(n_anchors))

        values['roc_auc']['micro'][n_anchors] = {
            'mean': float(np.mean(curr_values['roc_auc']['micro'], dtype=np.float32)),
            'std': float(np.std(curr_values['roc_auc']['micro'], dtype=np.float32))
        }
        mlflow.log_metric('mean_roc_auc_micro',
                          float(np.mean(curr_values['roc_auc']['micro'], dtype=np.float32)),
                          int(n_anchors))

        # all_macro_fpr, mean_macro_tpr = get_mean_tprs(curr_values['fpr']['macro'], curr_values['tpr']['macro'])
        # values['roc']['macro'][n_anchors] = {
        #     'fpr': all_macro_fpr,
        #     'tpr': mean_macro_tpr
        # }
        #
        # all_micro_fpr, mean_micro_tpr = get_mean_tprs(curr_values['fpr']['micro'], curr_values['tpr']['micro'])
        # values['roc']['micro'][n_anchors] = {
        #     'fpr': all_micro_fpr,
        #     'tpr': mean_micro_tpr
        # }

        for key in families:
            values['roc_auc'][key][n_anchors] = {
                'mean': float(np.mean(curr_values['roc_auc'][key], dtype=np.float32)),
                'std': float(np.std(curr_values['roc_auc'][key], dtype=np.float32))
            }
            mlflow.log_metric('mean_roc_auc_{}'.format(key),
                              float(np.mean(curr_values['roc_auc'][key], dtype=np.float32)),
                              int(n_anchors))

            # all_f_fpr, mean_f_tpr = get_mean_tprs(curr_values['fpr'][key], curr_values['tpr'][key])
            # values['roc'][key][n_anchors] = {
            #     'fpr': all_f_fpr,
            #     'tpr': mean_f_tpr
            # }

    with tempfile.TemporaryDirectory() as tmpdir:
        auc_macro_filename = os.path.join(tmpdir, 'auc_roc_macro.png')
        auc_micro_filename = os.path.join(tmpdir, 'auc_roc_micro.png')
        plot_score_trend(values['roc_auc']['macro'], filename=auc_macro_filename, key='auc-roc_macro', style=('k', '-'))
        plot_score_trend(values['roc_auc']['micro'], filename=auc_micro_filename, key='auc-roc_micro', style=('k', '-'))

        mlflow.log_artifact(auc_macro_filename, 'fresh_scores_plots')
        mlflow.log_artifact(auc_micro_filename, 'fresh_scores_plots')

        for fam in families:
            auc_f_filename = os.path.join(tmpdir, 'auc_roc_{}.png'.format(fam))
            plot_score_trend(values['roc_auc'][fam], filename=auc_f_filename, key='auc-roc_{}'.format(fam),
                             style=('k', '-'))

            mlflow.log_artifact(auc_f_filename, 'fresh_scores_plots')


@baker.command
def compute_all_fresh_results(results_file):
    # start mlflow run
    with mlflow.start_run():
        compute_fresh_scores(predictions_json_path=results_file)

        plot_fresh_results(predictions_json_path=results_file)


def get_fresh_dataset_info(ds_path):  # fresh dataset root directory (where to find .dat files)
    """ Get some fresh_dataset specific variables.

    Args:
        ds_path: Fresh dataset root directory (where to find .dat files)
    Returns:
        all_families, n_families, style_dict
    """

    # load fresh dataset generator
    generator = get_generator(ds_root=ds_path,
                              batch_size=1000,
                              return_shas=False,
                              shuffle=False)

    # get label to signature function from the dataset (used to convert numerical labels to family names)
    label_to_sig = generator.dataset.label_to_sig

    # get total number of families in fresh dataset
    n_families = generator.dataset.n_families

    # compute all families list
    all_families = [label_to_sig(i) for i in range(n_families)]

    # combine the previously defined information into a "style" dictionary (e.g. {'loki': ('r', ':'), ..})
    style_dict = {fam: (color, linestyle) for fam, color, linestyle in zip(all_families,
                                                                           default_family_colors,
                                                                           default_family_linestyles)}

    return all_families, n_families, style_dict


def plot_family_results(dataframe,  # result dataframe
                        filename,  # the name of the file where to save the resulting plot
                        families,  # families (list) to extract results for
                        style_dict):  # style dictionary (e.g. {'loki': ('r', ':'), ..})
    """ Produce multiple overlaid ROC plots (one for each family individually) and save the overall figure to file.

    Args:
        dataframe: Result dataframe
        filename: The name of the file where to save the resulting plot
        families: Families (list) to extract results for
        style_dict: Style dictionary (e.g. {'loki': ('r', ':'), ..})
    """

    # calculate ROC curve for each family of the current (single) run and create a family - ROC curve dictionary
    all_fam_rocs = {fam: get_roc_curve(dataframe, fam) for fam in families}

    # interpolate ROC curves and get fpr (false positive rate) points and interpolated tprs (true positive rates)
    eval_fpr_pts, interpolated_rocs = interpolate_rocs(all_fam_rocs)

    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))

    # for each family
    for fam in families:
        # use a default style
        color, linestyle = style_dict[fam.split('_')[1]]

        # calculate AUC (area under (ROC) curve) score
        auc = get_auc_score(dataframe, fam)

        # log auc as metric
        mlflow.log_metric("{}_auc".format(fam), auc, step=0)

        # plot ROC curve
        plt.semilogx(  # make a plot with log scaling on the x axis
            eval_fpr_pts,  # false positive rate points as 'x' values
            interpolated_rocs[fam],  # interpolated true positive rates for the current family as 'y' values
            color + linestyle,  # format string, e.g. 'ro' for red circles
            linewidth=2.0,  # line width in points
            label=f"{fam.split('_')[1]} (AUC):{auc:5.3f}")  # label that will be displayed in the legend

    # place legend in the location, among the nine possible locations, with the minimum overlap with other drawn objects
    plt.legend(loc='best')
    plt.xlim(1e-6, 1.0)  # set the x plot limits
    plt.ylim([0., 1.])  # set the y plot limits
    plt.xlabel('False Positive Rate (FPR)')  # set the label for the x-axis
    plt.ylabel('True Positive Rate (TPR)')  # set the label for the y-axis
    plt.title("Per-family ROC curve")  # set plot title
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure


def plot_family_mean_results(id_to_dataframe_dictionary,  # run ID - result dataframe dictionary
                             filename,  # the name of the file where to save the resulting plot
                             families,  # families (list) to extract results for
                             style_dict):  # style dictionary (e.g. {'loki': ('r', ':'), ..})
    """ Produce multiple overlaid ROC plots (one for each family individually) and save the overall figure to file.

    Args:
        id_to_dataframe_dictionary: Run ID - result dataframe dictionary
        filename: The name of the file where to save the resulting plot
        families: Families (list) to extract results for
        style_dict: Style dictionary (e.g. {'loki': ('r', ':'), ..})
    """

    # if the length of the run ID - result dataframe dictionary is not grater than 1
    if not len(id_to_dataframe_dictionary) > 1:
        # raise an exception
        raise ValueError("Need a minimum of 2 result sets to plot confidence region; found {}".format(
            len(id_to_dataframe_dictionary)
        ))

    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))

    # for each family
    for fam in families:
        # calculate ROC curve for each run and create a run ID - ROC curve dictionary
        id_to_roc_dictionary = {k: get_roc_curve(df, fam) for k, df in id_to_dataframe_dictionary.items()}

        # interpolate ROC curves and get fpr (false positive rate) points and interpolated tprs (true positive rates)
        fpr_points, interpolated_tprs = interpolate_rocs(id_to_roc_dictionary)

        # stack the interpolated_tprs arrays in sequence vertically -> I obtain a vertical vector of vectors (each of
        # which has all the interpolated values for one single run)
        tpr_array = np.vstack([v for v in interpolated_tprs.values()])

        # calculate mean tpr along dim 0 -> (for each fpr point under examination I calculate the mean along all runs)
        mean_tpr = tpr_array.mean(0)

        # calculate AUC (area under (ROC) curve) score for each run and store them into a numpy array
        aucs = np.array([get_auc_score(v, fam) for v in id_to_dataframe_dictionary.values()])

        # calculate the mean ROC AUC score along all runs
        mean_auc = aucs.mean()

        # use a default style
        color, linestyle = style_dict[fam.split('_')[1]]

        # log mean auc as metric
        mlflow.log_metric("{}_mean_auc".format(fam), mean_auc, step=0)

        # plot ROC curve
        plt.semilogx(  # make a plot with log scaling on the x axis
            fpr_points,  # false positive rate points as 'x' values
            mean_tpr,  # interpolated mean true positive rates for the current family as 'y' values
            color + linestyle,  # format string, e.g. 'ro' for red circles
            linewidth=2.0,  # line width in points
            label=f"{fam.split('_')[1]} (AUC mean):{mean_auc:5.3f}")  # label that will be displayed in the legend

    # place legend in the location, among the nine possible locations, with the minimum overlap with other drawn objects
    plt.legend(loc='best')
    plt.xlim(1e-6, 1.0)  # set the x plot limits
    plt.ylim([0., 1.])  # set the y plot limits
    plt.xlabel('False Positive Rate (FPR)')  # set the label for the x-axis
    plt.ylabel('True Positive Rate (TPR)')  # set the label for the y-axis
    plt.title("Per-family mean ROC curve")  # set plot title
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure


def compute_run_scores(results_file,  # path to results.csv containing the output of a model run
                       families,  # families (list) to extract results for
                       zero_division=1.0):  # sets the value to return when there is a zero division
    """ Compute all scores for all families.

    Args:
        results_file: Path to results.csv containing the output of a model run
        families: Families (list) to extract results for
        zero_division: Sets the value to return when there is a zero division
    """

    # crete temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        # for each family in all_families list, compute scores
        for fam in families:
            output_filename = os.path.join(tempdir, fam + "_scores.csv")

            compute_scores(results_file=results_file,
                           key=fam,
                           dest_file=output_filename,
                           zero_division=zero_division)

            # log output file as artifact
            mlflow.log_artifact(output_filename, "refined_model_fresh_scores")


def plot_run_results(results_file,  # path to results.csv containing the output of a model run
                     families,  # families (list) to extract results for
                     style_dict):  # style dictionary (e.g. {'loki': ('r', ':'), ..})
    """ Takes a result file from a feedforward neural network model that includes all families, and produces multiple
    overlaid ROC plots for each family individually.

    Args:
        results_file: Path to results.csv containing the output of a model run
        families: Families (list) to extract results for
        style_dict: Style dictionary (e.g. {'loki': ('r', ':'), ..})
    """

    # create run ID - filename correspondence dictionary (containing just one result file)
    id_to_resultfile_dict = {'run': results_file}

    # read csv result file and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    # create temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        output_filename = os.path.join(tempdir, "refined_model_results.png")

        # produce multiple overlaid ROC plots (one for each family individually) and save the overall figure to file
        plot_family_results(dataframe=id_to_dataframe_dict['run'],
                            filename=output_filename,
                            families=families,
                            style_dict=style_dict)

        # log output file as artifact
        mlflow.log_artifact(output_filename, "refined_model_fresh_results")


def plot_mean_results(run_to_filename_json,  # A json file that contains a key-value map that links run
                      # IDs to the full path to a results file (including the file name)
                      all_families,  # list of all families to plot results of
                      style_dict):  # style dictionary (e.g. {'loki': ('r', ':'), ..})
    """ Computes the mean of the TPR at a range of FPRS (the ROC curve) over several sets of results (at least 2 runs)
        for all families (provided) and produces multiple overlaid ROC plots for each family individually.
        The run_to_filename_json file must have the following format:
        {"run_id_0": "/full/path/to/results.csv/for/run/0/fresh_results.csv",
         "run_id_1": "/full/path/to/results.csv/for/run/1/fresh_results.csv",
          ...
        }

    Args:
        run_to_filename_json: A json file that contains a key-value map that links run IDs to the full path to a
                              results file (including the file name)
        all_families: List of all families to plot results of
        style_dict: Style dictionary (e.g. {'loki': ('r', ':'), ..})
    """

    # open json containing run ID - filename correspondences and decode it as json object
    id_to_resultfile_dict = json.load(open(run_to_filename_json, 'r'))

    # read csv result files and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    # create temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        output_filename = os.path.join(tempdir, "all_mean_fresh_results.png")

        # produce multiple overlaid ROC plots (one for each family individually) and save the overall figure to file
        plot_family_mean_results(id_to_dataframe_dictionary=id_to_dataframe_dict,
                                 filename=output_filename,
                                 families=all_families,
                                 style_dict=style_dict)

        # log output file as artifact
        mlflow.log_artifact(output_filename, "refined_model_fresh_results")


def plot_single_roc_distribution(run_to_filename_json,  # A json file that contains a key-value map that links run
                                 # IDs to the full path to a results file (including the file name)
                                 style_dict,  # style dictionary (e.g. {'loki': ('r', ':'), ..})
                                 fam_to_plot,  # the family from the results to plot
                                 linestyle=None,  # the linestyle to use in the plot (if None use some defaults)
                                 color=None,  # the color to use in the plot (if None use some defaults)
                                 include_range=False,  # plot the min/max value as well
                                 std_alpha=.2,  # the alpha value for the shading for standard deviation range
                                 range_alpha=.1):  # the alpha value for the shading for range, if plotted
    """ Compute the mean and standard deviation of the TPR at a range of FPRS (the ROC curve) over several sets of
    results (at least 2 runs) for a given family. The run_to_filename_json file must have the following format:
    {"run_id_0": "/full/path/to/results.csv/for/run/0/fresh_results.csv",
     "run_id_1": "/full/path/to/results.csv/for/run/1/fresh_results.csv",
      ...
    }

    Args:
        run_to_filename_json: A json file that contains a key-value map that links run IDs to the full path to a
                              results file (including the file name)
        style_dict: Style dictionary (e.g. {'loki': ('r', ':'), ..})
        fam_to_plot: The family from the results to plot
        linestyle: The linestyle to use in the plot (defaults to the family value in plot.style_dict)
        color: The color to use in the plot (defaults to the family value in plot.style_dict)
        include_range: Plot the min/max value as well (default False)
        std_alpha: The alpha value for the shading for standard deviation range (default 0.2)
        range_alpha: The alpha value for the shading for range, if plotted (default 0.1)
    """

    # open json containing run ID - filename correspondences and decode it as json object
    id_to_resultfile_dict = json.load(open(run_to_filename_json, 'r'))

    # read csv result files and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    if color is None or linestyle is None:  # if either color or linestyle is None
        if not (color is None and linestyle is None):  # if just one of them is None
            raise ValueError("both color and linestyle should either be specified or None")  # raise an exception

        # otherwise select default style
        style = style_dict[fam_to_plot]
    else:
        # otherwise (both color and linestyle were specified) define the style as a tuple of color and linestyle
        style = (color, linestyle)

    with tempfile.TemporaryDirectory() as tempdir:
        output_filename = os.path.join(tempdir, fam_to_plot + "_results.png")

        # plot roc curve with confidence
        plot_roc_with_confidence(id_to_dataframe_dictionary=id_to_dataframe_dict,
                                 key=fam_to_plot,
                                 filename=output_filename,
                                 include_range=include_range,
                                 style=style,
                                 std_alpha=std_alpha,
                                 range_alpha=range_alpha)

        # log output file as artifact
        mlflow.log_artifact(output_filename, "refined_model_fresh_results")


@baker.command
def compute_all_refined_results(results_file,  # path to results.csv containing the output of a model run
                                fresh_ds_path,  # fresh dataset root directory (where to find .dat files)
                                zero_division=1.0):  # sets the value to return when there is a zero division
    """ Takes a result file from a feedforward neural network model and produces results plots, computes per-family
        scores.

    Args:
        results_file: Path to results.csv containing the output of a model run
        fresh_ds_path: Fresh dataset root directory (where to find .dat files)
        zero_division: Sets the value to return when there is a zero division. If set to “warn”, this acts as 0,
                       but warnings are also raised
    """

    # start mlflow run
    with mlflow.start_run():
        # get some fresh_dataset related variables
        all_families, n_families, style_dict = get_fresh_dataset_info(ds_path=fresh_ds_path)

        # plot rocs for all families in the same figure
        plot_run_results(results_file=results_file,
                         families=all_families,
                         style_dict=style_dict)

        # compute all run scores
        compute_run_scores(results_file=results_file,
                           families=all_families,
                           zero_division=zero_division)


@baker.command
def plot_all_refined_roc_distributions(run_to_filename_json,  # run - filename json file path
                                       fresh_ds_path):  # fresh dataset root directory (where to find .dat files)
    """ Plot ROC distributions for all families.

    Args:
        run_to_filename_json: A json file that contains a key-value map that links run IDs to the full path to a
                              results file (including the file name)
        fresh_ds_path: Fresh dataset root directory (where to find .dat files)
    """

    # start mlflow run
    with mlflow.start_run():
        # get some fresh_dataset related variables
        all_families, n_families, style_dict = get_fresh_dataset_info(ds_path=fresh_ds_path)

        # plot mean rocs for all families in the same figure
        plot_mean_results(run_to_filename_json=run_to_filename_json,
                          all_families=all_families,
                          style_dict=style_dict)

        # for each family in all_families, compute and plot roc distribution
        for fam in all_families:
            plot_single_roc_distribution(run_to_filename_json=run_to_filename_json,
                                         fam_to_plot=fam,
                                         style_dict=style_dict)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
