import unreal
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()

class PublishUnrealFbx(HookBaseClass):
    def publish(self, settings, item):
        """
        Unreal에서 FBX를 익스포트하고 퍼블리시.
        """
        # 퍼블리시 경로 가져오기
        publish_path = item.properties["publish_path"]

        # Unreal에서 FBX 익스포트
        asset = item.properties.get("unreal_asset")
        if asset:
            unreal.ExporterFBX.export_asset(asset, publish_path)
            self.logger.info(f"FBX exported to: {publish_path}")
        else:
            self.logger.warning("No Unreal asset found to export.")
        
        # ShotGrid 퍼블리시 처리
        super(PublishUnrealFbx, self).publish(settings, item)
