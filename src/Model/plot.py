import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import tempfile  # used to create temporary files and directories

import baker  # easy, powerful access to Python functions from the command line
import matplotlib  # comprehensive library for creating static, animated, and interactive visualizations in Python
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
from logzero import logger  # robust and effective logging for Python
from sklearn.metrics import jaccard_score  # used to compute the Jaccard similarity coefficient score

from nets.generators.generators import Dataset
from utils.plot_utils import *

matplotlib.use('Agg')  # Select 'Agg' as the backend used for rendering and GUI integration

# define default tags
default_tags = ['adware_tag', 'flooder_tag', 'ransomware_tag',
                'dropper_tag', 'spyware_tag', 'packed_tag',
                'crypto_miner_tag', 'file_infector_tag', 'installer_tag',
                'worm_tag', 'downloader_tag']

# define default tag colors to be used in the graph
default_tag_colors = ['r', 'r', 'r',
                      'g', 'g', 'b',
                      'b', 'm', 'm',
                      'c', 'c']

# define default tag linestyles to be used in the graph
default_tag_linestyles = [':', '--', '-.',
                          ':', '--', ':',
                          '--', ':', '--',
                          ':', '--']

# combine the previously defined information into a "style" dictionary (e.g. {'adware_tag': ('r', ':'), ..})
style_dict = {tag: (color, linestyle) for tag, color, linestyle in zip(default_tags,
                                                                       default_tag_colors,
                                                                       default_tag_linestyles)}

# append style information for label 'malware'
style_dict['malware'] = ('k', '-')

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


def plot_tag_results(dataframe,  # result dataframe
                     filename,  # the name of the file where to save the resulting plot
                     tags):  # tags (list) to extract results for
    """ Produce multiple overlaid ROC plots (one for each tag individually) and save the overall figure to file.

    Args:
        dataframe: Result dataframe
        filename: The name of the file where to save the resulting plot
        tags: Tags (list) to extract results for
    """

    # calculate ROC curve for each tag of the current (single) run and create a tag - ROC curve dictionary
    all_tag_rocs = {tag: get_roc_curve(dataframe, tag) for tag in tags}

    # interpolate ROC curves and get fpr (false positive rate) points and interpolated tprs (true positive rates)
    eval_fpr_pts, interpolated_rocs = interpolate_rocs(all_tag_rocs)

    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))

    # for each tag
    for tag in tags:
        # use a default style
        color, linestyle = style_dict[tag]

        # calculate AUC (area under (ROC) curve) score
        auc = get_auc_score(dataframe, tag)

        # log auc as metric
        mlflow.log_metric("{}_auc".format(tag), auc, step=0)

        # plot ROC curve
        plt.semilogx(  # make a plot with log scaling on the x axis
            eval_fpr_pts,  # false positive rate points as 'x' values
            interpolated_rocs[tag],  # interpolated true positive rates for the current tag as 'y' values
            color + linestyle,  # format string, e.g. 'ro' for red circles
            linewidth=2.0,  # line width in points
            label=f"{tag} (AUC):{auc:5.3f}")  # label that will be displayed in the legend

    # place legend in the location, among the nine possible locations, with the minimum overlap with other drawn objects
    plt.legend(loc='best')
    plt.xlim(1e-6, 1.0)  # set the x plot limits
    plt.ylim([0., 1.])  # set the y plot limits
    plt.xlabel('False Positive Rate (FPR)')  # set the label for the x-axis
    plt.ylabel('True Positive Rate (TPR)')  # set the label for the y-axis
    plt.title("Per tag ROC curve")  # set plot title
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure


def plot_tag_mean_results(id_to_dataframe_dictionary,  # run ID - result dataframe dictionary
                          filename,  # the name of the file where to save the resulting plot
                          tags):  # tags (list) to extract results for
    """ Produce multiple overlaid ROC plots (one for each tag individually) and save the overall figure to file.

    Args:
        id_to_dataframe_dictionary: Run ID - result dataframe dictionary
        filename: The name of the file where to save the resulting plot
        tags: Tags (list) to extract results for
    """

    # if the length of the run ID - result dataframe dictionary is not grater than 1
    if not len(id_to_dataframe_dictionary) > 1:
        # raise an exception
        raise ValueError("Need a minimum of 2 result sets to plot confidence region; found {}".format(
            len(id_to_dataframe_dictionary)
        ))

    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))

    # for each tag
    for tag in tags:
        # calculate ROC curve for each run and create a run ID - ROC curve dictionary
        id_to_roc_dictionary = {k: get_roc_curve(df, tag) for k, df in id_to_dataframe_dictionary.items()}

        # interpolate ROC curves and get fpr (false positive rate) points and interpolated tprs (true positive rates)
        fpr_points, interpolated_tprs = interpolate_rocs(id_to_roc_dictionary)

        # stack the interpolated_tprs arrays in sequence vertically -> I obtain a vertical vector of vectors (each of
        # which has all the interpolated values for one single run)
        tpr_array = np.vstack([v for v in interpolated_tprs.values()])

        # calculate mean tpr along dim 0 -> (for each fpr point under examination I calculate the mean along all runs)
        mean_tpr = tpr_array.mean(0)

        # calculate AUC (area under (ROC) curve) score for each run and store them into a numpy array
        aucs = np.array([get_auc_score(v, tag) for v in id_to_dataframe_dictionary.values()])

        # calculate the mean ROC AUC score along all runs
        mean_auc = aucs.mean()

        # use a default style
        color, linestyle = style_dict[tag]

        # log mean auc as metric
        mlflow.log_metric("{}_mean_auc".format(tag), mean_auc, step=0)

        # plot ROC curve
        plt.semilogx(  # make a plot with log scaling on the x axis
            fpr_points,  # false positive rate points as 'x' values
            mean_tpr,  # interpolated mean true positive rates for the current tag as 'y' values
            color + linestyle,  # format string, e.g. 'ro' for red circles
            linewidth=2.0,  # line width in points
            label=f"{tag} (AUC mean):{mean_auc:5.3f}")  # label that will be displayed in the legend

    # place legend in the location, among the nine possible locations, with the minimum overlap with other drawn objects
    plt.legend(loc='best')
    plt.xlim(1e-6, 1.0)  # set the x plot limits
    plt.ylim([0., 1.])  # set the y plot limits
    plt.xlabel('False Positive Rate (FPR)')  # set the label for the x-axis
    plt.ylabel('True Positive Rate (TPR)')  # set the label for the y-axis
    plt.title("Per tag mean ROC curve")  # set plot title
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure


def compute_run_scores(results_file,  # path to results.csv containing the output of a model run
                       use_malicious_labels=1,  # whether or not (1/0) to compute malware/benignware label scores
                       use_tag_labels=1,  # whether or not (1/0) to compute the tag label scores
                       zero_division=1.0):  # sets the value to return when there is a zero division
    """ Compute all scores for all tags.

    Args:
        results_file: Path to results.csv containing the output of a model run
        use_malicious_labels: Whether or not (1/0) to compute malware/benignware label scores
        use_tag_labels: Whether or not (1/0) to compute the tag label scores
        zero_division: Sets the value to return when there is a zero division
    """

    # check use_malicious_labels and use_tag_labels, at least one of them should be 1,
    # otherwise the scores cannot be computed -> return
    if not bool(use_malicious_labels) and not bool(use_tag_labels):
        logger.warning('Both "use_malicious_labels" and "use_tag_labels" are set to 0 (false). Returning..')
        return

    # initialize all_tags as an empty list
    all_tags = []
    if bool(use_tag_labels):  # if use_tag_labels is 1, append the tags to all_tags list
        all_tags.extend([tag + "_tag" for tag in Dataset.tags])
    if bool(use_malicious_labels):  # if use_malicious_labels is 1, append malware label to all_tags list
        all_tags.append("malware")

    # crete temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        # for each tag in all_tags list, compute scores
        for tag in all_tags:
            output_filename = os.path.join(tempdir, tag + "_scores.csv")

            compute_scores(results_file=results_file,
                           key=tag,
                           dest_file=output_filename,
                           zero_division=zero_division)

            # log output file as artifact
            mlflow.log_artifact(output_filename, "model_scores")


def compute_run_mean_scores(results_file,  # path to results.csv containing the output of a model run
                            use_malicious_labels=1,  # whether or not to compute malware/benignware label scores
                            use_tag_labels=1,  # whether or not to compute the tag label scores
                            zero_division=1.0):  # sets the value to return when there is a zero division
    """ Estimate some mean, per-sample, scores (jaccard similarity and mean per-sample accuracy) for a dataframe at
    specific False Positive Rates of interest.

    Args:
        results_file: Path to results.csv containing the output of a model run
        use_malicious_labels: Whether or not (1/0) to compute malware/benignware label scores
        use_tag_labels: Whether or not (1/0) to compute the tag label scores
        zero_division: Sets the value to return when there is a zero division. If set to “warn”, this acts as 0,
                       but warnings are also raised
    """

    # if use_tag_labels is set to 0, the mean scores cannot be computed -> return
    if not bool(use_tag_labels):
        logger.warning('"use_tag_labels" is set to 0 (false).'
                       'Jaccard score is not available outside of multi-label classification. Returning..')
        return

    # initialize all_tags as a list containing all tags
    all_tags = [tag + "_tag" for tag in Dataset.tags]

    # create run ID - filename correspondence dictionary (containing just one result file)
    id_to_resultfile_dict = {'run': results_file}

    # read csv result file and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    # get labels, target fprs and predictions from current run results dataframe
    labels, target_fprs, predictions = get_all_predictions(id_to_dataframe_dict['run'], keys=all_tags)

    # compute jaccard scores at each target fpr
    jaccard_scores = np.asarray([jaccard_score(labels,
                                               predictions[i],
                                               average='samples',
                                               zero_division=zero_division)
                                 for i, fpr in enumerate(target_fprs)])

    # compute accuracy scores at each target fpr
    accuracy_scores = np.asarray([accuracy_score(labels,
                                                 predictions[i])
                                  for i, fpr in enumerate(target_fprs)])

    # create scores dataframe
    scores_df = pd.DataFrame({'fpr': target_fprs,
                              'mean jaccard similarity': jaccard_scores,
                              'mean per-sample accuracy': accuracy_scores},
                             index=list(range(1, len(target_fprs) + 1)))

    # create temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        output_filename = os.path.join(tempdir, "mean_per_sample_scores.csv")

        # open output file at the specified location
        with open(output_filename, "w") as output_file:
            # serialize scores_df dictionary as a json object and save it to file
            scores_df.to_csv(output_file)

        # log output file as artifact
        mlflow.log_artifact(output_filename, "model_mean_scores")


def plot_run_results(results_file,  # path to results.csv containing the output of a model run
                     use_malicious_labels=1,  # whether or not (1/0) to compute malware/benignware label scores
                     use_tag_labels=1):  # whether or not (1/0) to compute the tag label scores
    """ Takes a result file from a feedforward neural network model that includes all tags, and produces multiple
    overlaid ROC plots for each tag individually.

    Args:
        results_file: Path to results.csv containing the output of a model run
        use_malicious_labels: Whether or not (1/0) to compute malware/benignware label scores
        use_tag_labels: Whether or not (1/0) to compute the tag label scores
    """

    # check use_malicious_labels and use_tag_labels, at least one of them should be 1, otherwise the tag
    # results cannot be calulated -> return
    if not bool(use_malicious_labels) and not bool(use_tag_labels):
        logger.warning('Both "use_malicious_labels" and "use_tag_labels" are set to 0 (false). Returning..')
        return

    # initialize all_tags as an empty list
    all_tags = []
    if bool(use_tag_labels):  # if use_tag_labels is 1, append the tags to all_tags list
        all_tags.extend([tag + "_tag" for tag in Dataset.tags])
    if bool(use_malicious_labels):  # if use_malicious_labels is 1, append malware label to all_tags list
        all_tags.append("malware")

    # create run ID - filename correspondence dictionary (containing just one result file)
    id_to_resultfile_dict = {'run': results_file}

    # read csv result file and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    # create temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        output_filename = os.path.join(tempdir, "results.png")

        # produce multiple overlaid ROC plots (one for each tag individually) and save the overall figure to file
        plot_tag_results(id_to_dataframe_dict['run'], output_filename, tags=all_tags)

        # log output file as artifact
        mlflow.log_artifact(output_filename, "model_results")


def plot_mean_results(run_to_filename_json,  # A json file that contains a key-value map that links run
                      # IDs to the full path to a results file (including the file name)
                      all_tags):  # list of all tags to plot results of
    """ Computes the mean of the TPR at a range of FPRS (the ROC curve) over several sets of results (at least 2 runs)
        for all tags (provided) and produces multiple overlaid ROC plots for each tag individually.
        The run_to_filename_json file must have the following format:
        {"run_id_0": "/full/path/to/results.csv/for/run/0/results.csv",
         "run_id_1": "/full/path/to/results.csv/for/run/1/results.csv",
          ...
        }

    Args:
        run_to_filename_json: A json file that contains a key-value map that links run IDs to the full path to a
                              results file (including the file name)
        all_tags: List of all tags to plot results of
    """

    # open json containing run ID - filename correspondences and decode it as json object
    id_to_resultfile_dict = json.load(open(run_to_filename_json, 'r'))

    # read csv result files and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    # create temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        output_filename = os.path.join(tempdir, "all_mean_results.png")

        # produce multiple overlaid ROC plots (one for each tag individually) and save the overall figure to file
        plot_tag_mean_results(id_to_dataframe_dict, output_filename, tags=all_tags)

        # log output file as artifact
        mlflow.log_artifact(output_filename, "model_results")


def plot_single_roc_distribution(run_to_filename_json,  # A json file that contains a key-value map that links run
                                 # IDs to the full path to a results file (including the file name)
                                 tag_to_plot='malware',  # the tag from the results to plot
                                 linestyle=None,  # the linestyle to use in the plot (if None use some defaults)
                                 color=None,  # the color to use in the plot (if None use some defaults)
                                 include_range=False,  # plot the min/max value as well
                                 std_alpha=.2,  # the alpha value for the shading for standard deviation range
                                 range_alpha=.1):  # the alpha value for the shading for range, if plotted
    """ Compute the mean and standard deviation of the TPR at a range of FPRS (the ROC curve) over several sets of
    results (at least 2 runs) for a given tag. The run_to_filename_json file must have the following format:
    {"run_id_0": "/full/path/to/results.csv/for/run/0/results.csv",
     "run_id_1": "/full/path/to/results.csv/for/run/1/results.csv",
      ...
    }

    Args:
        run_to_filename_json: A json file that contains a key-value map that links run IDs to the full path to a
                              results file (including the file name)
        tag_to_plot: The tag from the results to plot; defaults to "malware"
        linestyle: The linestyle to use in the plot (defaults to the tag value in plot.style_dict)
        color: The color to use in the plot (defaults to the tag value in plot.style_dict)
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
        style = style_dict[tag_to_plot]
    else:
        # otherwise (both color and linestyle were specified) define the style as a tuple of color and linestyle
        style = (color, linestyle)

    with tempfile.TemporaryDirectory() as tempdir:
        output_filename = os.path.join(tempdir, tag_to_plot + "_results.png")

        # plot roc curve with confidence
        plot_roc_with_confidence(id_to_dataframe_dict,
                                 tag_to_plot,
                                 output_filename,
                                 include_range=include_range,
                                 style=style,
                                 std_alpha=std_alpha,
                                 range_alpha=range_alpha)

        # log output file as artifact
        mlflow.log_artifact(output_filename, "model_results")


@baker.command
def compute_all_run_results(results_file,  # path to results.csv containing the output of a model run
                            use_malicious_labels=1,  # whether or not (1/0) to compute malware/benignware label scores
                            use_tag_labels=1,  # whether or not (1/0) to compute the tag label scores
                            zero_division=1.0):  # sets the value to return when there is a zero division
    """ Takes a result file from a feedforward neural network model and produces results plots, computes per-tag scores
        and mean per-sample scores.

    Args:
        results_file: Path to results.csv containing the output of a model run
        use_malicious_labels: Whether or not (1/0) to compute malware/benignware label scores
        use_tag_labels: Whether or not (1/0) to compute the tag label scores
        zero_division: Sets the value to return when there is a zero division. If set to “warn”, this acts as 0,
                       but warnings are also raised
    """

    # start mlflow run
    with mlflow.start_run():
        # plot rocs for all tags in the same figure
        plot_run_results(results_file=results_file,
                         use_malicious_labels=use_malicious_labels,
                         use_tag_labels=use_tag_labels)

        # compute all per-tag scores
        compute_run_scores(results_file=results_file,
                           use_malicious_labels=use_malicious_labels,
                           use_tag_labels=use_tag_labels,
                           zero_division=zero_division)

        # compute mean per-sample scores
        compute_run_mean_scores(results_file=results_file,
                                use_malicious_labels=use_malicious_labels,
                                use_tag_labels=use_tag_labels,
                                zero_division=zero_division)


@baker.command
def plot_all_roc_distributions(run_to_filename_json,  # run - filename json file path
                               use_malicious_labels=1,  # whether or not (1/0) to compute malware label scores
                               use_tag_labels=1):  # whether or not (1/0) to compute the tag label scores
    """ Plot ROC distributions for all tags.

    Args:
        run_to_filename_json: A json file that contains a key-value map that links run IDs to the full path to a
                              results file (including the file name)
        use_malicious_labels: Whether or not (1/0) to compute malware/benignware label scores
        use_tag_labels: Whether or not (1/0) to compute the tag label scores
    """

    # start mlflow run
    with mlflow.start_run():
        # check use_malicious_labels and use_tag_labels, at least one of them should be 1, otherwise the roc
        # distributions cannot be calculated -> return
        if not bool(use_malicious_labels) and not bool(use_tag_labels):
            logger.warning('Both "use_malicious_labels" and "use_tag_labels" are set to 0 (false). Returning..')
            return

        # initialize all_tags as an empty list
        all_tags = []
        if bool(use_tag_labels):  # if use_tag_labels is 1, append the tags to all_tags list
            all_tags.extend([tag + "_tag" for tag in Dataset.tags])
        if bool(use_malicious_labels):  # if use_malicious_labels is 1, append malware label to all_tags list
            all_tags.append("malware")

        # plot mean rocs for all tags in the same figure
        plot_mean_results(run_to_filename_json=run_to_filename_json,
                          all_tags=all_tags)

        # for each tag in all_tags, compute and plot roc distribution
        for tag in all_tags:
            plot_single_roc_distribution(run_to_filename_json=run_to_filename_json,
                                         tag_to_plot=tag)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
