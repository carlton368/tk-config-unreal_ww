# This file is based on templates provided and copyrighted by Autodesk, Inc.
# This file has been modified by Epic Games, Inc. and is subject to the license
# file included in this repository.

import sgtk
import unreal
from tank_vendor import six

import copy
import datetime
import os
import pprint
import subprocess
import sys
import tempfile
import glob
# Local storage path field for known Oses.
_OS_LOCAL_STORAGE_PATH_FIELD = {
    "darwin": "mac_path",
    "win32": "windows_path",
    "linux": "linux_path",
    "linux2": "linux_path",
}[sys.platform]

HookBaseClass = sgtk.get_hook_baseclass()

# print("PUBLISH_MOVIE LOADING")
# if 'WONJIN_PUBLISH_MOVIE' in os.environ:
#     os.environ['WONJIN_PUBLISH_MOVIE'] += os.pathsep + 'PUBLISH_MOVIE_LOADING'
# else:
#     os.environ['WONJIN_PUBLISH_MOVIE'] = 'PUBLISH_MOVIE_LOADING'



class UnrealMoviePublishPlugin(HookBaseClass):
    """
    Plugin for publishing an Unreal sequence as a rendered movie file.

    This hook relies on functionality found in the base file publisher hook in
    the publish2 app and should inherit from it in the configuration. The hook
    setting for this plugin should look something like this::

        hook: "{self}/publish_file.py:{engine}/tk-multi-publish2/basic/publish_session.py"

    To learn more about writing a publisher plugin, visit
    http://developer.shotgunsoftware.com/tk-multi-publish2/plugin.html
    """
    def __init__(self, *args, **kwargs):
        super(UnrealMoviePublishPlugin, self).__init__(*args, **kwargs)
        print("PUBLISH_MOVIE INIT")
        if 'WONJIN_PUBLISH_MOVIE' in os.environ:
            os.environ['WONJIN_PUBLISH_MOVIE'] += os.pathsep + 'PUBLISH_MOVIE_INIT'
        else:
            os.environ['WONJIN_PUBLISH_MOVIE'] = 'PUBLISH_MOVIE_INIT'
    # NOTE: The plugin icon and name are defined by the base file plugin.

    @property
    def settings(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.
        """
        base_settings = super(UnrealMoviePublishPlugin, self).settings or {}
        base_settings["Publish Template"] = {
            "type": "template",
            "default": None,
            "description": "Template path for published work files. Should"
                        "correspond to a template defined in templates.yml.",
        }
        base_settings["Movie Render Queue Presets Path"] = {
            "type": "string",
            "default": None,
            "description": "Optional Unreal Path to saved presets for rendering with the Movie Render Queue"
        }
        base_settings["Publish Folder"] = {
            "type": "string",
            "default": None,
            "description": "Optional folder to use as a root for publishes"
        }
        base_settings["Render Format"] = {
            "type": "str",
            "default": "exr",
            "description": "Render output format: 'exr' or 'mov'"
        }

        return base_settings

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """
        return ["unreal.asset.LevelSequence"]

    def create_settings_widget(self, parent):
        """
        Creates a Qt widget, for the supplied parent widget (a container widget
        on the right side of the publish UI).

        :param parent: The parent to use for the widget being created
        :return: A :class:QtGui.QFrame that displays editable widgets for
                 modifying the plugin's settings.
        """
        # defer Qt-related imports
        from sgtk.platform.qt import QtGui, QtCore

        # Create a QFrame with all our widgets
        settings_frame = QtGui.QFrame(parent)
        # Create our widgets, we add them as properties on the QFrame so we can
        # retrieve them easily. Qt uses camelCase so our xxxx_xxxx names can't
        # clash with existing Qt properties.

        # Show this plugin description
        settings_frame.description_label = QtGui.QLabel(self.description)
        settings_frame.description_label.setWordWrap(True)
        settings_frame.description_label.setOpenExternalLinks(True)
        settings_frame.description_label.setTextFormat(QtCore.Qt.RichText)

        # Unreal setttings
        settings_frame.unreal_render_presets_label = QtGui.QLabel("Render with Movie Pipeline Presets:")
        settings_frame.unreal_render_presets_widget = QtGui.QComboBox()
        settings_frame.unreal_render_presets_widget.addItem("No presets")
        presets_folder = unreal.MovieRenderPipelineProjectSettings().preset_save_dir
        for preset in unreal.EditorAssetLibrary.list_assets(presets_folder.path):
            settings_frame.unreal_render_presets_widget.addItem(preset.split(".")[0])

        settings_frame.unreal_publish_folder_label = QtGui.QLabel("Publish folder:")
        storage_roots = self.parent.shotgun.find(
            "LocalStorage",
            [],
            ["code", _OS_LOCAL_STORAGE_PATH_FIELD]
        )
        settings_frame.storage_roots_widget = QtGui.QComboBox()
        settings_frame.storage_roots_widget.addItem("Current Unreal Project")
        for storage_root in storage_roots:
            if storage_root[_OS_LOCAL_STORAGE_PATH_FIELD]:
                settings_frame.storage_roots_widget.addItem(
                    "%s (%s)" % (
                        storage_root["code"],
                        storage_root[_OS_LOCAL_STORAGE_PATH_FIELD]
                    ),
                    userData=storage_root,
                )
        # Create the layout to use within the QFrame
        settings_layout = QtGui.QVBoxLayout()
        settings_layout.addWidget(settings_frame.description_label)
        settings_layout.addWidget(settings_frame.unreal_render_presets_label)
        settings_layout.addWidget(settings_frame.unreal_render_presets_widget)
        settings_layout.addWidget(settings_frame.unreal_publish_folder_label)
        settings_layout.addWidget(settings_frame.storage_roots_widget)

        settings_layout.addStretch()
        settings_frame.setLayout(settings_layout)
        return settings_frame

    def get_ui_settings(self, widget):
        """
        Method called by the publisher to retrieve setting values from the UI.

        :returns: A dictionary with setting values.
        """
        # defer Qt-related imports
        from sgtk.platform.qt import QtCore

        self.logger.info("Getting settings from UI")

        # Please note that we don't have to return all settings here, just the
        # settings which are editable in the UI.
        render_presets_path = None
        if widget.unreal_render_presets_widget.currentIndex() > 0:  # First entry is "No Presets"
            render_presets_path = six.ensure_str(widget.unreal_render_presets_widget.currentText())
        storage_index = widget.storage_roots_widget.currentIndex()
        publish_folder = None
        if storage_index > 0:  # Something selected and not the first entry
            storage = widget.storage_roots_widget.itemData(storage_index, role=QtCore.Qt.UserRole)
            publish_folder = storage[_OS_LOCAL_STORAGE_PATH_FIELD]

        settings = {
            "Movie Render Queue Presets Path": render_presets_path,
            "Publish Folder": publish_folder,
        }
        return settings

    def set_ui_settings(self, widget, settings):
        """
        Method called by the publisher to populate the UI with the setting values.

        :param widget: A QFrame we created in create_settings_widget.
        :param settings: A list of dictionaries.
        :raises NotImplementedError: if editing multiple items.
        """
        # defer Qt-related imports
        from sgtk.platform.qt import QtCore

        self.logger.info("Setting UI settings")
        if len(settings) > 1:
            # We do not allow editing multiple items
            raise NotImplementedError
        cur_settings = settings[0]
        render_presets_path = cur_settings["Movie Render Queue Presets Path"]
        preset_index = 0
        if render_presets_path:
            preset_index = widget.unreal_render_presets_widget.findText(render_presets_path)
            self.logger.info("Index for %s is %s" % (render_presets_path, preset_index))
        widget.unreal_render_presets_widget.setCurrentIndex(preset_index)
        # Note: the template is validated in the accept method, no need to check it here.
        publish_template_setting = cur_settings.get("Publish Template")
        publisher = self.parent
        publish_template = publisher.get_template_by_name(publish_template_setting)
        if isinstance(publish_template, sgtk.TemplatePath):
            widget.unreal_publish_folder_label.setEnabled(False)
            widget.storage_roots_widget.setEnabled(False)
        folder_index = 0
        publish_folder = cur_settings["Publish Folder"]
        if publish_folder:
            for i in range(widget.storage_roots_widget.count()):
                data = widget.storage_roots_widget.itemData(i, role=QtCore.Qt.UserRole)
                if data and data[_OS_LOCAL_STORAGE_PATH_FIELD] == publish_folder:
                    folder_index = i
                    break
            self.logger.debug("Index for %s is %s" % (publish_folder, folder_index))
        widget.storage_roots_widget.setCurrentIndex(folder_index)

    def load_saved_ui_settings(self, settings):
        """
        Load saved settings and update the given settings dictionary with them.

        :param settings: A dictionary where keys are settings names and
                         values Settings instances.
        """
        # Retrieve SG utils framework settings module and instantiate a manager
        fw = self.load_framework("tk-framework-shotgunutils_v5.x.x")
        module = fw.import_module("settings")
        settings_manager = module.UserSettings(self.parent)

        # Retrieve saved settings
        settings["Movie Render Queue Presets Path"].value = settings_manager.retrieve(
            "publish2.movie_render_queue_presets_path",
            settings["Movie Render Queue Presets Path"].value,
            settings_manager.SCOPE_PROJECT,
        )
        settings["Publish Folder"].value = settings_manager.retrieve(
            "publish2.publish_folder",
            settings["Publish Folder"].value,
            settings_manager.SCOPE_PROJECT
        )
        self.logger.debug("Loaded settings %s" % settings["Publish Folder"])
        self.logger.debug("Loaded settings %s" % settings["Movie Render Queue Presets Path"])

    def save_ui_settings(self, settings):
        """
        Save UI settings.

        :param settings: A dictionary of Settings instances.
        """
        # Retrieve SG utils framework settings module and instantiate a manager
        fw = self.load_framework("tk-framework-shotgunutils_v5.x.x")
        module = fw.import_module("settings")
        settings_manager = module.UserSettings(self.parent)

        # Save settings
        render_presets_path = settings["Movie Render Queue Presets Path"].value
        settings_manager.store("publish2.movie_render_queue_presets_path", render_presets_path, settings_manager.SCOPE_PROJECT)
        publish_folder = settings["Publish Folder"].value
        settings_manager.store("publish2.publish_folder", publish_folder, settings_manager.SCOPE_PROJECT)

    def accept(self, settings, item):
        """
        Determines if the item is of any interest to this plugin.
        Remove publish_template logic here and simply load saved UI settings.
        """
        accepted = True
        checked = True

        if sys.platform != "win32":
            self.logger.warning("Movie publishing is not supported on other platforms than Windows...")
            return {
                "accepted": False,
            }

        # Don't load a template here, just load saved UI settings
        self.load_saved_ui_settings(settings)

        return {
            "accepted": accepted,
            "checked": checked
        }

    def validate(self, settings, item):
        asset_path = item.properties.get("asset_path")
        asset_name = item.properties.get("asset_name")
        if not asset_path or not asset_name:
            self.logger.debug("Sequence path or name not configured.")
            return False

        edits_path = item.properties.get("edits_path")
        if not edits_path:
            self.logger.debug("Edits path not configured.")
            return False

        self.logger.info("Edits path %s" % edits_path)
        item.properties["unreal_master_sequence"] = edits_path[0]
        item.properties["unreal_shot"] = ".".join([lseq.get_name() for lseq in edits_path[1:]])
        self.logger.info("Master sequence %s, shot %s" % (
            item.properties["unreal_master_sequence"].get_name(),
            item.properties["unreal_shot"] or "all shots",
        ))

        # Render Format 설정
        render_format = settings["Render Format"].value.lower()
        if render_format not in ["exr", "mov"]:
            self.logger.error("Render Format setting must be 'exr' or 'mov'. Given: %s" % render_format)
            return False
        self._render_format = render_format

        publisher = self.parent
        # render_format에 따라 템플릿 선택 (unreal.movie_publish_exr / unreal.movie_publish_mov)
        if render_format == "exr":
            publish_template = publisher.get_template_by_name("unreal.movie_publish_exr")
        else:
            publish_template = publisher.get_template_by_name("unreal.movie_publish_mov")

        if not publish_template:
            self.logger.error("Unable to find a publish template for format: %s" % render_format)
            return False

        context = item.context

        # 폴더 생성 확인
        if not context.filesystem_locations:
            if context.entity:
                tk = self.parent.sgtk
                self.logger.info("No filesystem structure found for context. Creating folders for %s %s"
                                % (context.entity["type"], context.entity["id"]))
                tk.create_filesystem_structure(context.entity["type"], context.entity["id"])

                if not context.filesystem_locations:
                    self.logger.error("Folders could not be created automatically. Please run folder creation manually.")
                    return False
            else:
                self.logger.error("No filesystem structure found and context has no entity. "
                                "Cannot create folders. Please ensure folders exist.")
                return False

        fields = context.as_template_fields(publish_template)

        # Step 필드 필요 시
        if 'Step' in publish_template.keys:
            if context.step:
                fields["Step"] = context.step["name"]
            else:
                self.logger.error("Context does not have a Step defined, but the template requires it.")
                return False

        # Sequence 필드 필요 시 Shot으로부터 Sequence 가져오기
        if 'Sequence' in publish_template.keys and context.entity and context.entity["type"] == "Shot":
            sg = self.parent.shotgun
            shot_data = sg.find_one("Shot", [["id", "is", context.entity["id"]]], ["sg_sequence"])
            if shot_data and shot_data["sg_sequence"]:
                fields["Sequence"] = shot_data["sg_sequence"]["name"]
                self.logger.info("Retrieved sequence %s from context." % shot_data["sg_sequence"]["name"])
            else:
                self.logger.warning("No sequence found for shot %s, but template requires Sequence." % context.entity["name"])

        # Shot 필드 필요 시 설정
        if 'Shot' in publish_template.keys and context.entity and context.entity["type"] == "Shot":
            fields["Shot"] = context.entity["name"]

        # Unreal World, Level Sequence 설정
        unreal_map = unreal.EditorLevelLibrary.get_editor_world()
        unreal_map_path = unreal_map.get_path_name()
        if unreal_map_path.startswith("/Temp/"):
            self.logger.debug("Current map must be saved first.")
            return False
        world_name = unreal_map.get_name()
        fields["ue_world"] = world_name

        edits_path_count = len(edits_path)
        if edits_path_count > 1:
            fields["ue_level_sequence"] = "%s_%s" % (edits_path[0].get_name(), edits_path[-1].get_name())
        else:
            fields["ue_level_sequence"] = edits_path[0].get_name()

        item.properties["unreal_asset_path"] = asset_path
        item.properties["unreal_map_path"] = unreal_map_path

        # 첫 퍼블리시시 v001로 시작하도록 고정. 
        # 에셋 메타데이터나 파일명 재분석 로직 제거.
        version_number = 1
        fields["version"] = version_number

        date = datetime.date.today()
        fields["YYYY"] = date.year
        fields["MM"] = date.month
        fields["DD"] = date.day

        sequence = unreal.EditorAssetLibrary.load_asset(asset_path)
        if isinstance(sequence, unreal.LevelSequence):
            playback_range = sequence.get_playback_range()
            fps = sequence.get_display_rate()
            start_frame = playback_range.get_start_frame()
            end_frame = playback_range.get_end_frame() - 1
            item.properties["start_frame"] = start_frame
            item.properties["end_frame"] = end_frame
            item.properties["frame_rate"] = fps.numerator
            self.logger.info("Sequence frame range: %d to %d at %d fps" % (start_frame, end_frame, fps.numerator))

        # 누락 키 확인
        missing_keys = publish_template.missing_keys(fields)
        if missing_keys:
            self.logger.error("Missing keys required for the publish template: {}".format(missing_keys))
            return False

        publish_folder = settings["Publish Folder"].value
        if not publish_folder:
            publish_folder = unreal.Paths.project_saved_dir()

        publish_path = publish_template.apply_fields(fields)
        publish_path = os.path.abspath(os.path.join(publish_folder, publish_path))

        item.properties["path"] = publish_path
        item.properties["publish_path"] = publish_path
        item.properties["version_number"] = version_number
        item.properties["publish_version"] = version_number

        if self._render_format == "exr":
            item.properties["publish_type"] = "Rendered Image Sequence"
        else:
            item.properties["publish_type"] = "Rendered Movie"

        item.properties["fields"] = fields

        # Movie Render Queue presets
        use_movie_render_queue = False
        render_presets = None
        if hasattr(unreal, "MoviePipelineQueueEngineSubsystem"):
            use_movie_render_queue = True
            self.logger.info("Movie Render Queue will be used for rendering.")
            render_presets_path = settings["Movie Render Queue Presets Path"].value
            if render_presets_path:
                self.logger.info("Validating render presets path %s" % render_presets_path)
                render_presets = unreal.EditorAssetLibrary.load_asset(render_presets_path)
                for _, reason in self._check_render_settings(render_presets):
                    self.logger.warning(reason)

        item.properties["use_movie_render_queue"] = use_movie_render_queue
        item.properties["movie_render_queue_presets"] = render_presets

        self.save_ui_settings(settings)
        return True

    def _check_render_settings(self, render_config):
        """
        Check settings from the given render preset and report which ones are problematic.
        Now we allow both EXR image sequence and Apple ProRes outputs.
        """
        invalid_settings = []
        allowed_outputs = (
            unreal.MoviePipelineImageSequenceOutput_EXR,
            unreal.MoviePipelineAppleProResOutput  
        )

        for setting in render_config.get_all_settings():
            if isinstance(setting, unreal.MoviePipelineImagePassBase) and type(setting) != unreal.MoviePipelineDeferredPassBase:
                invalid_settings.append((setting, "Render pass %s would cause multiple outputs" % setting.get_name()))
            elif isinstance(setting, unreal.MoviePipelineOutputBase) and not isinstance(setting, allowed_outputs):
                invalid_settings.append((setting, "Render output %s is not allowed" % setting.get_name()))
        return invalid_settings

    def publish(self, settings, item):
        publish_path = os.path.normpath(item.properties["publish_path"])
        destination_folder, base_name = os.path.split(publish_path)
        base_name = os.path.splitext(base_name)[0]

        fields = item.properties["fields"]
        version_number = item.properties["version_number"]

        if item.properties.get("use_movie_render_queue"):
            presets = item.properties["movie_render_queue_presets"]
            if presets:
                self.logger.info("Rendering %s with the Movie Render Queue with %s presets." % (publish_path, presets.get_name()))
            else:
                self.logger.info("Rendering %s with the Movie Render Queue." % publish_path)
            res, output_dir = self._unreal_render_sequence_with_movie_queue(
                publish_path,
                item.properties["unreal_map_path"],
                item.properties["unreal_asset_path"],
                presets,
                item.properties.get("unreal_shot") or None
            )
        else:
            self.logger.info("Rendering %s with the Level Sequencer." % publish_path)
            res, output_dir = self._unreal_render_sequence_with_sequencer(
                publish_path,
                item.properties["unreal_map_path"],
                item.properties["unreal_asset_path"]
            )

        if not res:
            raise RuntimeError("Unable to render %s sequence at %s" % (self._render_format, publish_path))

        self._unreal_asset_set_version(item.properties["unreal_asset_path"], version_number)

        if self._render_format == "exr":
            exr_files = sorted([f for f in glob.glob(os.path.join(output_dir, base_name + "_*.exr")) if os.path.isfile(f)])
            if not exr_files:
                raise RuntimeError("No EXR frames found after rendering.")
            exr_pattern = os.path.join(output_dir, base_name + "%04d.exr")
            item.properties["path"] = exr_pattern
            item.properties["publish_path"] = exr_pattern
        else:
            mov_files = sorted([f for f in glob.glob(os.path.join(output_dir, base_name + "_*.mov")) if os.path.isfile(f)])
            if not mov_files:
                raise RuntimeError("No MOV file found after rendering.")
            mov_file = mov_files[0]
            item.properties["path"] = mov_file
            item.properties["publish_path"] = mov_file

        super(UnrealMoviePublishPlugin, self).publish(settings, item)

    def finalize(self, settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are Setting
            instances.
        :param item: Item to process
        """
        # do the base class finalization
        super(UnrealMoviePublishPlugin, self).finalize(settings, item)

    def _get_version_entity(self, item):
        """
        Returns the best entity to link the version to.
        """
        if item.context.entity:
            return item.context.entity
        elif item.context.project:
            return item.context.project
        else:
            return None

    def _unreal_asset_get_version(self, asset_path):
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        version_number = 0

        if not asset:
            return version_number

        engine = sgtk.platform.current_engine()
        tag = engine.get_metadata_tag("version_number")

        metadata = unreal.EditorAssetLibrary.get_metadata_tag(asset, tag)

        if not metadata:
            return version_number

        try:
            version_number = int(metadata)
        except ValueError:
            pass

        return version_number

    def _unreal_asset_set_version(self, asset_path, version_number):
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)

        if not asset:
            return

        engine = sgtk.platform.current_engine()
        tag = engine.get_metadata_tag("version_number")

        unreal.EditorAssetLibrary.set_metadata_tag(asset, tag, str(version_number))
        unreal.EditorAssetLibrary.save_loaded_asset(asset)


        engine = sgtk.platform.current_engine()
        for dialog in engine.created_qt_dialogs:
            dialog.raise_()

    def _unreal_render_sequence_with_sequencer(self, output_path, unreal_map_path, sequence_path):
        if self._render_format == "exr":
            movie_format = "Image"
            extension = "exr"
        else:
            movie_format = "Video"
            extension = "mov"

        output_folder, output_file = os.path.split(output_path)
        movie_name = os.path.splitext(output_file)[0].replace('.', '_')

        engine_root = unreal.Paths.engine_dir()
        editor_cmd_path = os.path.join(engine_root, "Binaries", "Win64", "UnrealEditor-Cmd.exe")
        if not os.path.isfile(editor_cmd_path):
            editor_cmd_path = os.path.join(engine_root, "Binaries", "Win64", "UnrealEditor.exe")

        cmdline_args = [
            editor_cmd_path,
            "%s" % os.path.join(
                unreal.SystemLibrary.get_project_directory(),
                "%s.uproject" % unreal.SystemLibrary.get_game_name(),
            ),
            unreal_map_path,
            "-LevelSequence=%s" % sequence_path,
            "-MovieFolder=%s" % output_folder,
            "-MovieName=%s" % movie_name,
            "-game",
            "-MovieSceneCaptureType=/Script/MovieSceneCapture.AutomatedLevelSequenceCapture",
            "-ResX=1280",
            "-ResY=720",
            "-ForceRes",
            "-Windowed",
            "-MovieCinematicMode=yes",
            "-MovieFormat=%s" % movie_format,
            "-MovieExtension=%s" % extension,
            "-MovieFrameRate=24",
            "-MovieQuality=75",
            "-NoTextureStreaming",
            "-NoLoadingScreen",
            "-NoScreenMessages",
        ]

        run_env = copy.copy(os.environ)
        if "UE_SHOTGUN_BOOTSTRAP" in run_env:
            del run_env["UE_SHOTGUN_BOOTSTRAP"]
        if "UE_SHOTGRID_BOOTSTRAP" in run_env:
            del run_env["UE_SHOTGRID_BOOTSTRAP"]

        subprocess.call(cmdline_args, env=run_env)

        pattern = os.path.join(output_folder, movie_name + "*." + extension)
        files = sorted([f for f in glob.glob(pattern) if os.path.isfile(f)])
        return (len(files) > 0), output_folder

    def _unreal_render_sequence_with_movie_queue(self, output_path, unreal_map_path, sequence_path, presets=None, shot_name=None):
        # self._render_format에 따라 Movie Render Queue 설정
        output_folder, output_file = os.path.split(output_path)
        movie_name = os.path.splitext(output_file)[0].replace('.', '_')

        qsub = unreal.MoviePipelineQueueEngineSubsystem()
        queue = qsub.get_queue()
        job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
        job.sequence = unreal.SoftObjectPath(sequence_path)
        job.map = unreal.SoftObjectPath(unreal_map_path)

        if shot_name:
            shot_found = False
            for shot in job.shot_info:
                if shot.outer_name != shot_name:
                    shot.enabled = False
                else:
                    shot_found = True
            if not shot_found:
                raise ValueError("Unable to find shot %s in sequence %s, aborting..." % (shot_name, sequence_path))

        if presets:
            job.set_preset_origin(presets)

        config = job.get_configuration()
        output_setting = config.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
        output_setting.output_directory = unreal.DirectoryPath(output_folder)
        output_setting.output_resolution = unreal.IntPoint(1280, 720)
        output_setting.file_name_format = movie_name + "_{frame_number}"
        output_setting.override_existing_output = True

        # 불필요한 출력 제거 후 self._render_format에 맞게 출력 설정
        for setting_class in [unreal.MoviePipelineImageSequenceOutput_EXR, unreal.MoviePipelineAppleProResOutput]:
            existing = config.find_settings_by_class(setting_class)
            for e in existing:
                config.remove_setting(e)

        if self._render_format == "exr":
            config.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_EXR)
        else:
            config.find_or_add_setting_by_class(unreal.MoviePipelineAppleProResOutput)

        config.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)

        _, manifest_path = unreal.MoviePipelineEditorLibrary.save_queue_to_manifest_file(queue)
        manifest_path = os.path.abspath(manifest_path)
        manifest_dir, manifest_file = os.path.split(manifest_path)
        f, new_path = tempfile.mkstemp(suffix=os.path.splitext(manifest_file)[1], dir=manifest_dir)
        os.close(f)
        os.replace(manifest_path, new_path)
        manifest_path = new_path.replace(
            "%s%s" % (
                os.path.abspath(
                    os.path.join(unreal.SystemLibrary.get_project_directory(), "Saved")
                ),
                os.path.sep,
            ),
            "",
        )

        engine_root = unreal.Paths.engine_dir()
        editor_cmd_path = os.path.join(engine_root, "Binaries", "Win64", "UnrealEditor-Cmd.exe")
        if not os.path.isfile(editor_cmd_path):
            editor_cmd_path = os.path.join(engine_root, "Binaries", "Win64", "UnrealEditor.exe")

        cmd_args = [
            editor_cmd_path,
            "%s" % os.path.join(
                unreal.SystemLibrary.get_project_directory(),
                "%s.uproject" % unreal.SystemLibrary.get_game_name(),
            ),
            "MoviePipelineEntryMap?game=/Script/MovieRenderPipelineCore.MoviePipelineGameMode",
            "-game",
            "-Multiprocess",
            "-NoLoadingScreen",
            "-FixedSeed",
            "-log",
            "-Unattended",
            "-messaging",
            '-SessionName="Publish2 Movie Render"',
            "-nohmd",
            "-windowed",
            "-ResX=1280",
            "-ResY=720",
            "-dpcvars=%s" % ",".join([
                "sg.ViewDistanceQuality=4",
                "sg.AntiAliasingQuality=4",
                "sg.ShadowQuality=4",
                "sg.PostProcessQuality=4",
                "sg.TextureQuality=4",
                "sg.EffectsQuality=4",
                "sg.FoliageQuality=4",
                "sg.ShadingQuality=4",
                "r.TextureStreaming=0",
                "r.ForceLOD=0",
                "r.SkeletalMeshLODBias=-10",
                "r.ParticleLODBias=-10",
                "foliage.DitheredLOD=0",
                "foliage.ForceLOD=0",
                "r.Shadow.DistanceScale=10",
                "r.ShadowQuality=5",
                "r.Shadow.RadiusThreshold=0.001000",
                "r.ViewDistanceScale=50",
                "r.D3D12.GPUTimeout=0",
                "a.URO.Enable=0",
            ]),
            "-execcmds=r.HLOD 0",
            '-MoviePipelineConfig="%s"' % manifest_path,
        ]

        run_env = copy.copy(os.environ)
        if "UE_SHOTGUN_BOOTSTRAP" in run_env:
            del run_env["UE_SHOTGUN_BOOTSTRAP"]
        if "UE_SHOTGRID_BOOTSTRAP" in run_env:
            del run_env["UE_SHOTGRID_BOOTSTRAP"]
        self.logger.info("Running %s" % cmd_args)
        subprocess.call(cmd_args, env=run_env)

        pattern = os.path.join(output_folder, movie_name + "_*." + self._render_format)
        frames = sorted([f for f in glob.glob(pattern) if os.path.isfile(f)])
        return (len(frames) > 0), output_folder