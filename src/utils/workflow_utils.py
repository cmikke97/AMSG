import base64  # provides functions for encoding/decoding binary data to/from printable ASCII characters
import hashlib  # implements a common interface to many different secure hash and message digest algorithms

import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
from logzero import logger  # robust and effective logging for Python
from mlflow.entities import RunStatus  # status of a Run
from mlflow.tracking.fluent import _get_experiment_id  # get current experiment id function
from mlflow.utils import mlflow_tags  # mlflow tags


class Hash:
    """ Simple wrapper around hashlib sha256 functions. """

    def __init__(self):
        """ Initialize hash class using hashlib sha256 implementation. """

        # initialize sha256 hash object
        self.m = hashlib.sha256()

    def update(self,
               w):  # string to update hash value with
        """ Update current hash value.

        Args:
            w: String to update hash value with
        """

        # update current hash with w
        self.m.update(w.encode('utf-8'))

    def copy(self):
        """ Return a copy of the Hash object

        Returns:
            Copy of the current Hash instance
        """
        # instantiate new hash object
        copy = Hash()
        # copy current object sha256 into the new instance
        copy.m = self.m.copy()
        # return the new instance
        return copy

    def get_b64(self):
        """ Get base64 encoding of the current hash value digest.

        Returns:
            Base64 encoding of the hash digest.
        """

        # return base64 encoded (url safe) hash digest
        return base64.urlsafe_b64encode(self.m.digest()).decode('utf-8')


def _already_ran(entry_point_name,  # entry point name of the run
                 parameters,  # parameters of the run
                 git_commit,  # git version of the code run
                 config_sha,  # sha256 of config file
                 ignore_git=False,  # whether to ignore git version or not (default: False)
                 experiment_id=None,  # experiment id (default: None)
                 resume=False):  # whether to resume a failed/killed previous run or not (default: False)
    """ Best-effort detection of if a run with the given entrypoint name, parameters, and experiment id already ran.
    The run must have completed successfully and have at least the parameters provided.

    Args:
        entry_point_name: Entry point name of the run
        parameters: Parameters of the run
        git_commit: Git version of the code run
        config_sha: Sha256 of config file
        ignore_git: Whether to ignore git version or not (default: False)
        experiment_id: Experiment id (default: None)
        resume: Whether to resume a failed/killed previous run (only for training) or not (default: False)
    Returns:
        Previously executed run if found, None otherwise.
    """

    # if experiment ID is not provided retrieve current experiment ID
    experiment_id = experiment_id if experiment_id is not None else _get_experiment_id()
    # instantiate MLflowClient (creates and manages experiments and runs)
    client = mlflow.tracking.MlflowClient()
    # get reversed list of run information (from last to first)
    all_run_infos = reversed(client.list_run_infos(experiment_id))

    run_to_resume_id = None

    # for all runs info
    for run_info in all_run_infos:
        # fetch run from backend store
        full_run = client.get_run(run_info.run_id)
        # get run dictionary of tags
        tags = full_run.data.tags
        # if there is no entry point, or the entry point for the run is different from 'entry_point_name', continue
        if tags.get(mlflow_tags.MLFLOW_PROJECT_ENTRY_POINT, None) != entry_point_name:
            continue

        # initialize 'match_failed' bool to false
        match_failed = False
        # for each parameter in the provided run parameters
        for param_key, param_value in parameters.items():
            # get run param value from the run dictionary of parameters
            run_value = full_run.data.params.get(param_key)
            # if the current parameter value is different from the run parameter set 'match_failed' to true and break
            if str(run_value) != str(param_value):
                match_failed = True
                break
        # if the current run is not the one we are searching for go to the next one
        if match_failed:
            continue

        # get previous run git commit version
        previous_version = tags.get(mlflow_tags.MLFLOW_GIT_COMMIT, None)
        # if the previous version is different from the current one, go to the next one
        if not ignore_git and git_commit != previous_version:
            logger.warning("Run matched, but has a different source version, so skipping (found={}, expected={})"
                           .format(previous_version, git_commit))
            continue

        # get config file sha256 from the run
        run_config_sha = full_run.data.params.get('config_sha')
        # if the config file sha256 for the run is different from the current sha, go to the next one
        if str(run_config_sha) != str(config_sha):
            logger.warning("Run matched, but config is different.")
            continue

        # if the run is not finished
        if run_info.to_proto().status != RunStatus.FINISHED:
            if resume:
                # if resume is enabled, set current run to resume id -> if no newer completed run is found,
                # this stopped run will be resumed
                run_to_resume_id = run_info.run_id
                continue
            else:  # otherwise skip it and try with the next one
                logger.warning("Run matched, but is not FINISHED, so skipping " "(run_id={}, status={})"
                               .format(run_info.run_id, run_info.status))
                continue

        # otherwise (if the run was found and it is exactly the same), return the found run
        return client.get_run(run_info.run_id)

    # if no previously executed (and finished) run was found but a stopped run was found, resume such run
    if run_to_resume_id is not None:
        logger.info("Resuming run with entrypoint=%s and parameters=%s" % (entry_point_name, parameters))
        # update new run parameters with the stopped run id
        parameters.update({
            'run_id': run_to_resume_id
        })
        # submit new run that will resume the previously interrupted one
        submitted_run = mlflow.run(".", entry_point_name, parameters=parameters)

        # log config file sha256 as parameter in the submitted run
        client.log_param(submitted_run.run_id, 'config_sha', config_sha)

        # return submitted (new) run
        return mlflow.tracking.MlflowClient().get_run(submitted_run.run_id)

    # if the searched run was not found return 'None'
    logger.warning("No matching run has been found.")
    return None


def run(entrypoint,  # entrypoint of the run
        parameters,  # parameters of the run
        config_sha):  # sha256 of config file
    """ Launch run.

    Args:
        entrypoint: Entrypoint of the run
        parameters: Parameters of the run
        config_sha: Sha256 of config file
    Returns:
        Launched run.
    """

    # get mlflow tracking client
    client = mlflow.tracking.MlflowClient()

    logger.info("Launching new run for entrypoint={} and parameters={}".format(entrypoint, parameters))
    # submit (start) run
    submitted_run = mlflow.run(".", entrypoint, parameters=parameters)

    # log config file sha256 as parameter in the submitted run
    client.log_param(submitted_run.run_id, 'config_sha', config_sha)

    # return run
    return client.get_run(submitted_run.run_id)


def get_or_run(entrypoint,  # entrypoint of the run
               parameters,  # parameters of the run
               git_commit,  # git version of the run
               config_sha,  # sha256 of config file
               ignore_git=False,  # whether to ignore git version or not (default: False)
               use_cache=True,  # whether to cache previous runs or not (default: True)
               resume=False):  # whether to resume a failed/killed previous run or not (default: False)
    """ Get previously executed run, if it exists, or launch run.

    Args:
        entrypoint: Entrypoint of the run
        parameters: Parameters of the run
        git_commit: Git version of the run
        config_sha: Sha256 of config file
        ignore_git: Whether to ignore git version or not (default: False)
        use_cache: Whether to cache previous runs or not (default: True)
        resume: Whether to resume a failed/killed previous run or not (default: False)
    Returns:
        Found or launched run.
    """

    # get already executed run, if it exists
    existing_run = _already_ran(entrypoint, parameters, git_commit,
                                ignore_git=ignore_git, resume=resume, config_sha=config_sha)
    # if we want to cache previous runs and we found a previously executed run, return found run
    if use_cache and existing_run:
        logger.info("Found existing run for entrypoint={} and parameters={}".format(entrypoint, parameters))
        return existing_run
    # otherwise, start run and return it
    return run(entrypoint=entrypoint, parameters=parameters, config_sha=config_sha)
