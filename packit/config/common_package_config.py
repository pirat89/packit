# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

"""
Common package config attributes so they can be imported both in PackageConfig and JobConfig
"""
import logging
import warnings
from enum import Enum
from os import getenv
from os.path import basename
from re import split
from typing import Any, Optional, Union

from packit.actions import ActionName
from packit.config.commands import TestCommandConfig
from packit.config.notifications import (
    NotificationsConfig,
)
from packit.config.requirements import RequirementsConfig
from packit.config.sources import SourcesItem
from packit.constants import DISTGIT_INSTANCES
from packit.dist_git_instance import DistGitInstance
from packit.exceptions import PackitConfigException
from packit.sync import SyncFilesItem, iter_srcs


class Deployment(Enum):
    dev = "dev"
    stg = "stg"
    prod = "prod"


def _construct_dist_git_instance(
    base_url: Optional[str],
    namespace: Optional[str],
    pkg_tool: Optional[str],
) -> DistGitInstance:
    """Construct a dist-git instance information from provided configuration.

    Args:
        base_url: Base URL of the dist-git provided from the config.
        namespace: Namespace in the dist-git provided from the config.
        pkg_tool: Packaging tool to be used provided from the config.

    Returns:
        Dist-git instance information that is used in config.
    """

    # explicitly specified values in config override everything
    if base_url is not None:
        return DistGitInstance.from_url_and_namespace(base_url, namespace)

    # explicitly specified packaging tool overrides too
    if pkg_tool:
        return DISTGIT_INSTANCES[pkg_tool]

    # we try the environment variables
    base_url, namespace = getenv("DISTGIT_URL"), getenv("DISTGIT_NAMESPACE")
    if base_url is not None:
        return DistGitInstance.from_url_and_namespace(base_url, namespace)

    # if nothing has been provided, default to the Fedora
    return DISTGIT_INSTANCES["fedpkg"]


class CommonPackageConfig:
    """Common configuration

    Attributes:
        config_file_path: Path of the configuration file from which this
            configuration was read.
        specfile_path: Path of the specfile in the upstream repo.
        _files_to_sync: List of files to be synced from the upstream
            repo to dist-git.
        _file_to_sync_used: Whether the _files_to_sync config is used.
            Flag used to provide backwards compatibility with 'synced_files'.
        synced_files: Deprecated. List of files to be synced from the upstream
            repo to dist-git.
        patch_generation_ignore_paths: Paths in the upstream repo to be ignored when
            generating patches.
        patch_generation_patch_id_digits: Number of digits used to produce patch IDs when
            adding 'PatchN' tags to the specfile.
        upstream_project_url: URL of the upstream project.
        upstream_project_name: Name of the upstream project.
        downstream_package_name: Name of the package downstream (i.e. in dist-git)
        paths: List of relative paths in the upstream repository, which should be
            considered for this package.
        _downstream_project_url: Deprecated. URL of the dist-git repo.
        dist_git_base_url: Base URL of the dist-git forge where the downstream package is
            stored.
        dist_git_namespace: Namespace in dist-git where the downstream package
            is stored.
        actions: Custom steps used during different operations.
        upstream_ref: The ref used for the last upstream release.
        allowed_gpg_keys: GPG-key fingerprints allowed to sign commits to be
            proposed to dist-git.
        create_pr: Whether to create a PR when proposing an update to dist-git.
        sync_changelog: Sync the changelog part of the specfile when proposing
            and update to dist-git.
        create_sync_note: Whether to create README.packit when proposing an
            update to dist-git.
        spec_source_id: The 'Source' tag in the specfile to be updated.
        spec_source_id_number: The numeric part of the above
        notifications: Notifications to send on a successful build.
        identifier: Suffix to be added to checks. Used to differentiate check flags
            which otherwise would have identical names.
        packit_instances: Packit-as-a-Service instances to be used.
        upstream_tag_template: Template used to transform version numbers to Git-tags.
        archive_root_dir_template: Template to generate the root directory used
            in source archives.
        copy_upstream_release_description: Use the GitHub release notes to update
            the changelog when proposing updates to dist-git.
        sources: URLs to sources to be used during SRPM builds (source-git specific).
        merge_pr_in_ci: Whether to merge a PR in the main branch prior to building.
        srpm_build_deps: Additional dependencies needed by SRPM builds.
        issue_repository: Repo were issues for downstream job failures (Koji builds,
            Bodhi updates) should be filed.
        release_suffix: String that can be used to override the default release
            suffix generated by Packit.
        update_release: Whether to update Release.
        _targets: copr_build, mock chroots where to build tests, builds to test.
            The _ prefix is used because 'targets' without it is now used for
            backward compatibility.
        timeout: copr_build, give up watching a build after timeout, defaults to 7200s
        owner: copr_build, a namespace in COPR where the build should happen
        project: copr_build, a name of the copr project
        dist_git_branches: propose_downstream, branches in dist-git where packit should work
        branch: for `commit` trigger to specify the branch name
        scratch: if we want to run scratch build in koji
        list_on_homepage: if set, created copr project will be visible on copr's home-page
        preserve_project: if set, project will not be created as temporary
        additional_packages: buildroot packages for the chroot [DOES NOT WORK YET]
        additional_repos: buildroot additional additional_repos
        fmf_url: - git repository containing the metadata (FMF) tree
        fmf_ref: - branch, tag or commit specifying the desired git revision
        fmf_path: - path to the fmf root
        use_internal_tf: if we want to use internal instance of Testing Farm
        skip_build: if we want to skip build phase for Testing Farm job
        env: environment variables
        enable_net: if set to False, Copr builds have network disabled
        allowed_pr_authors: List of Fedora accounts for which distgit PRs we
            will run koji builds.
        allowed_committers: List of Fedora accounts for which distgit pushes we
            will run koji builds.
        tmt_plan: Test to run in Testing Farm.
        tf_post_install_script: post install script to run before the tf tests
        tf_extra_params: Additional Testing Farm parameters to merge into the
            payload of TF requests.
        module_hotfixes: if set, copr will generate repo files with module_hotfixes=1
        upload_sources: If Packit should upload sources to lookaside cache. True by default.
        pkg_tool: Tool that is used for interaction with the lookaside cache.
        version_update_mask: String containing a reg exp. The old version contained in the
            specfile and the newly released version have both to match this reg exp
            otherwise Packit shall not sync the release downstream.
        parse_time_macros: Dict with macros to (un)define before parsing specfile.
            Keys are macro names and values are macro values. A value of None will undefine
            the corresponding macro.
    """

    def __init__(
        self,
        config_file_path: Optional[str] = None,
        specfile_path: Optional[str] = None,
        synced_files: Optional[list[SyncFilesItem]] = None,
        files_to_sync: Optional[list[SyncFilesItem]] = None,
        dist_git_namespace: Optional[str] = None,
        upstream_project_url: Optional[str] = None,  # can be URL or path
        upstream_package_name: Optional[str] = None,
        paths: Optional[list[str]] = None,
        downstream_project_url: Optional[str] = None,
        downstream_package_name: Optional[str] = None,
        dist_git_base_url: Optional[str] = None,
        actions: Optional[dict[ActionName, Union[str, list[str]]]] = None,
        upstream_ref: Optional[str] = None,
        allowed_gpg_keys: Optional[list[str]] = None,
        create_pr: bool = True,
        sync_changelog: bool = False,
        create_sync_note: bool = True,
        spec_source_id: str = "Source0",
        upstream_tag_template: str = "{version}",
        archive_root_dir_template: str = "{upstream_pkg_name}-{version}",
        patch_generation_ignore_paths: Optional[list[str]] = None,
        patch_generation_patch_id_digits: int = 4,
        notifications: Optional[NotificationsConfig] = None,
        copy_upstream_release_description: bool = False,
        sources: Optional[list[SourcesItem]] = None,
        merge_pr_in_ci: bool = True,
        srpm_build_deps: Optional[list[str]] = None,
        identifier: Optional[str] = None,
        packit_instances: Optional[list[Deployment]] = None,
        issue_repository: Optional[str] = None,
        release_suffix: Optional[str] = None,
        update_release: bool = True,
        # Former JobMetadataConfig attributes
        _targets: Union[list[str], dict[str, dict[str, Any]], None] = None,
        timeout: int = 7200,
        owner: Optional[str] = None,
        project: Optional[str] = None,
        dist_git_branches: Optional[list[str]] = None,
        branch: Optional[str] = None,
        scratch: bool = False,
        list_on_homepage: bool = False,
        preserve_project: bool = False,
        additional_packages: Optional[list[str]] = None,
        additional_repos: Optional[list[str]] = None,
        fmf_url: Optional[str] = None,
        fmf_ref: Optional[str] = None,
        fmf_path: Optional[str] = None,
        use_internal_tf: bool = False,
        skip_build: bool = False,
        env: Optional[dict[str, Any]] = None,
        enable_net: bool = False,
        allowed_pr_authors: Optional[list[str]] = None,
        allowed_committers: Optional[list[str]] = None,
        tmt_plan: Optional[str] = None,
        tf_post_install_script: Optional[str] = None,
        tf_extra_params: Optional[dict[Any, Any]] = None,
        module_hotfixes: bool = False,
        # # vm-image-build
        # example: "rhel-86"
        image_distribution: Optional[str] = None,
        image_request: Optional[dict] = None,
        image_customizations: Optional[dict] = None,
        copr_chroot: Optional[str] = None,
        follow_fedora_branching: bool = False,
        upstream_tag_include: str = "",
        upstream_tag_exclude: str = "",
        prerelease_suffix_pattern: str = r"([.\-_~^]?)(alpha|beta|rc|pre(view)?)([.\-_]?\d+)?",
        prerelease_suffix_macro: Optional[str] = None,
        upload_sources: bool = True,
        pkg_tool: Optional[str] = None,
        version_update_mask: Optional[str] = None,
        test_command: Optional[TestCommandConfig] = None,
        parse_time_macros: Optional[dict[str, str]] = None,
        require: Optional[RequirementsConfig] = None,
    ):
        self.config_file_path: Optional[str] = config_file_path
        self.specfile_path: Optional[str] = specfile_path

        self._files_to_sync: list[SyncFilesItem] = files_to_sync or []  # new option
        self._files_to_sync_used: bool = files_to_sync is not None
        self.synced_files: list[SyncFilesItem] = (
            synced_files or []
        )  # old deprecated option
        if synced_files is not None:
            self._warn_user()

        self.patch_generation_ignore_paths = patch_generation_ignore_paths or []
        self.patch_generation_patch_id_digits = patch_generation_patch_id_digits
        self.upstream_project_url: Optional[str] = upstream_project_url
        self.upstream_package_name: Optional[str] = upstream_package_name
        self.paths = paths or ["./"]
        # this is generated by us
        self.downstream_package_name: Optional[str] = downstream_package_name
        self._downstream_project_url: str = downstream_project_url

        # Set up the dist-git instance
        self.dist_git_instance = _construct_dist_git_instance(
            base_url=dist_git_base_url,
            namespace=dist_git_namespace,
            pkg_tool=pkg_tool,
        )

        self.actions = actions or {}
        self.upstream_ref: Optional[str] = upstream_ref
        self.allowed_gpg_keys = allowed_gpg_keys
        self.create_pr: bool = create_pr
        self.sync_changelog: bool = sync_changelog
        self.create_sync_note: bool = create_sync_note
        self.spec_source_id: str = spec_source_id
        self.notifications = notifications or NotificationsConfig()
        self.identifier = identifier

        # The default is set also on schema level,
        # but for sake of code-generated configs,
        # we want to react on prod events only by default.
        self.packit_instances = (
            packit_instances if packit_instances is not None else [Deployment.prod]
        )

        # template to create an upstream tag name (upstream may use different tagging scheme)
        self.upstream_tag_template = upstream_tag_template
        self.archive_root_dir_template = archive_root_dir_template
        self.copy_upstream_release_description = copy_upstream_release_description
        self.sources = sources or []
        self.merge_pr_in_ci = merge_pr_in_ci
        self.srpm_build_deps = srpm_build_deps
        self.issue_repository = issue_repository
        self.release_suffix = release_suffix
        self.update_release = update_release
        self.upstream_tag_include = upstream_tag_include
        self.upstream_tag_exclude = upstream_tag_exclude
        self.version_update_mask = version_update_mask
        self.prerelease_suffix_pattern = prerelease_suffix_pattern
        self.prerelease_suffix_macro = prerelease_suffix_macro
        self.test_command = test_command or TestCommandConfig()
        self.require = require or RequirementsConfig()

        # from deprecated JobMetadataConfig
        self._targets: dict[str, dict[str, Any]]
        if isinstance(_targets, list):
            self._targets = {key: {} for key in _targets}
        else:
            self._targets = _targets or {}
        self.timeout: int = timeout
        self.owner: str = owner
        self.project: str = project
        self.dist_git_branches: set[str] = (
            set(dist_git_branches) if dist_git_branches else set()
        )
        self.branch: str = branch
        self.scratch: bool = scratch
        self.list_on_homepage: bool = list_on_homepage
        self.preserve_project: bool = preserve_project
        self.additional_packages: list[str] = additional_packages or []
        self.additional_repos: list[str] = additional_repos or []
        self.fmf_url: str = fmf_url
        self.fmf_ref: str = fmf_ref
        self.fmf_path: str = fmf_path
        self.use_internal_tf: bool = use_internal_tf
        self.skip_build: bool = skip_build
        self.env: dict[str, Any] = env or {}
        self.enable_net = enable_net
        self.allowed_pr_authors = (
            allowed_pr_authors if allowed_pr_authors is not None else ["packit"]
        )
        self.allowed_committers = allowed_committers or []
        self.tmt_plan = tmt_plan
        self.tf_extra_params = tf_extra_params or {}
        self.tf_post_install_script = tf_post_install_script
        self.module_hotfixes = module_hotfixes

        self.image_distribution = image_distribution
        self.image_request = image_request
        self.image_customizations = image_customizations
        self.copr_chroot = copr_chroot

        self.follow_fedora_branching = follow_fedora_branching
        self.upload_sources = upload_sources

        self.pkg_tool = pkg_tool

        self.parse_time_macros = parse_time_macros or {}

    @property
    def dist_git_base_url(self) -> str:
        return self.dist_git_instance.url

    @property
    def dist_git_namespace(self) -> Optional[str]:
        return self.dist_git_instance.namespace

    @property
    def targets_dict(self):
        return self._targets

    @property
    def targets(self):
        """For backward compatibility."""
        return set(self._targets.keys())

    def _warn_user(self):
        logger = logging.getLogger(__name__)
        msg = "synced_files option is deprecated. Use files_to_sync option instead."
        logger.warning(msg)
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        if self._files_to_sync_used:
            logger.warning(
                "You are setting both files_to_sync and synced_files."
                " Packit will use files_to_sync. You should remove "
                "synced_files since it is deprecated.",
            )

    @property
    def files_to_sync(self) -> list[SyncFilesItem]:
        """
        synced_files is the old option we want to deprecate.
        Spec file and configuration file can be automatically added to
        the list of synced_files (see get_all_files_to_sync method)

        files_to_sync is the new option. Files to be synced are just those listed here.
        Spec file and configuration file will not be automatically added
        to the list of files_to_sync (see get_all_files_to_sync method).

        files_to_sync has precedence over synced_files.

        Once the old option will be removed this method can be removed as well.
        """

        if self._files_to_sync_used:
            return self._files_to_sync
        if self.synced_files:
            return self.synced_files
        return []

    def __repr__(self):
        # required to avoid cyclical imports
        from packit.schema import CommonConfigSchema

        s = CommonConfigSchema()
        # For __repr__() return a JSON-encoded string, by using dumps().
        # Mind the 's'!
        return f"CommonPackageConfig: {s.dumps(self)}"

    def __eq__(self, other: object):
        if not isinstance(other, CommonPackageConfig):
            raise PackitConfigException(
                "Provided object is not a CommonPackageConfig instance.",
            )
        # required to avoid cyclical imports
        from packit.schema import CommonConfigSchema

        s = CommonConfigSchema()
        # Compare the serialized objects.
        return s.dump(self) == s.dump(other)

    @property
    def downstream_project_url(self) -> str:
        if not self._downstream_project_url:
            self._downstream_project_url = self.dist_git_package_url
        return self._downstream_project_url

    @property
    def dist_git_package_url(self):
        if self.downstream_package_name:
            return (
                f"{self.dist_git_base_url}{self.dist_git_namespace}/"
                f"{self.downstream_package_name}.git"
            )
        return None

    @property
    def spec_source_id_number(self) -> int:
        """
        Return spec_source_id as a number, reverse of spec_source_id_fm
        """
        return int(next(iter(split(r"(\d+)", self.spec_source_id)[1:]), 0))

    def get_specfile_sync_files_item(self, from_downstream: bool = False):
        """
        Get SyncFilesItem object for the specfile.
        :param from_downstream: True when syncing from downstream
        :return: SyncFilesItem
        """
        upstream_specfile_path = self.specfile_path
        downstream_specfile_path = (
            f"{self.downstream_package_name}.spec"
            if self.downstream_package_name
            else basename(upstream_specfile_path)
        )
        return SyncFilesItem(
            src=[
                downstream_specfile_path if from_downstream else upstream_specfile_path,
            ],
            dest=upstream_specfile_path
            if from_downstream
            else downstream_specfile_path,
        )

    def get_all_files_to_sync(self):
        """
        Adds the default files (config file, spec file) to synced files
        if the new files_to_sync option is not yet used otherwise
        do not performer any addition to the list of files to be synced.

        When the old option will be removed this method could be removed as well.

        :return: Files to be synced
        """
        files = self.files_to_sync

        if not self._files_to_sync_used:
            if self.specfile_path not in iter_srcs(files):
                files.append(self.get_specfile_sync_files_item())

            if self.config_file_path and self.config_file_path not in iter_srcs(files):
                # this relative because of glob: "Non-relative patterns are unsupported"
                files.append(
                    SyncFilesItem(
                        src=[self.config_file_path],
                        dest=self.config_file_path,
                    ),
                )

        return files


class MultiplePackages:
    """
    Base class for configuration classes which have a "packages" attribute

    TODO: remove this once support to access the attributes of a single package
          is dropped.

    Notes:
        1. Need to define '__setattr__', b/c some properties of the config
           objects are set here and there. This makes it necessary to use the
           'super().__setattr__()' syntax when writing attributes of this
           class.
        2. In theory accessing attributes of this class with 'self.<attribute>'
           works, until it doesn't. Objects being deepcopied is one such
           case. Using 'self.__getattribute__("attribute")' solves this issue.
    """

    def __init__(self, packages: dict[str, CommonPackageConfig]):
        super().__setattr__("packages", packages)
        super().__setattr__("_first_package", next(iter(packages)))

    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        if len(self.__getattribute__("packages")) == 1:
            package = self.__getattribute__("packages")[
                self.__getattribute__("_first_package")
            ]
            return getattr(package, name)
        raise AttributeError(
            f"It is ambiguous to get {name}: "
            "there is more than one package in the config.",
        )

    def __setattr__(self, name, value):
        if name in self.__dict__ or "packages" not in self.__dict__:
            super().__setattr__(name, value)
        elif len(self.__getattribute__("packages")) == 1:
            package = self.__getattribute__("packages")[
                self.__getattribute__("_first_package")
            ]
            setattr(package, name, value)
        else:
            raise AttributeError(
                f"It is ambiguous to set {name}: "
                "there is more than one package in the config.",
            )

    def get_package_names_as_env(self) -> dict[str, str]:
        """Creates a dict with package_name,
        downstream_package_name and upstream_package_name.

        If the config contains multiple packages
        raise an Exception.
        """
        if len(self.packages) == 1:
            for packit_package_name, package_config in self.packages.items():
                env = {}
                env["PACKIT_CONFIG_PACKAGE_NAME"] = packit_package_name
                env["PACKIT_UPSTREAM_PACKAGE_NAME"] = (
                    package_config.upstream_package_name or ""
                )
                env["PACKIT_DOWNSTREAM_PACKAGE_NAME"] = (
                    package_config.downstream_package_name or ""
                )
                return env
            raise PackitConfigException("No packages in config")
        raise PackitConfigException("Multiple packages in config")
