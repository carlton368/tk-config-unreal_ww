# config/hooks/launch_python.py

import os
import sys
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()

class LaunchPython(HookBaseClass):
    def execute(self, app_path, app_args, version, **kwargs):
        """
        The execute function of the hook will be called to start the required application
        """
        # 부모 클래스의 prepare_launch 실행
        env = self.prepare_launch(app_path, app_args)

        # 찾은 FBX SDK 경로 설정
        fbx_sdk_path = r"C:\Users\lee\miniconda3\envs\fbx_env\lib\site-packages"

        # 기존 PYTHONPATH에 FBX SDK 경로 추가
        pythonpath = os.environ.get("PYTHONPATH", "")
        if pythonpath:
            pythonpath = f"{fbx_sdk_path}{os.pathsep}{pythonpath}"
        else:
            pythonpath = fbx_sdk_path
        env["PYTHONPATH"] = pythonpath

        # Conda 환경 경로도 추가
        env["CONDA_PREFIX"] = r"C:\Users\lee\miniconda3\envs\fbx_env"

        # 업데이트된 환경 변수로 Python 실행
        result = self.parent.execute_hook_method(
            "hook_launch_python",
            "execute_command",
            app_path=app_path,
            app_args=app_args,
            env=env
        )

        return result