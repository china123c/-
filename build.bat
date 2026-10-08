@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/4] 安装依赖...
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [2/4] 生成图标...
python make_icon.py

echo [3/4] 打包 exe（需要几分钟，请耐心等待）...
python -m PyInstaller --onefile --windowed --noconfirm --clean --name "历史剪贴板-快捷版" --icon icon.png main.py

echo [4/4] 完成！
echo.
echo 程序位置：dist\历史剪贴板-快捷版.exe
echo 把它放进一个固定文件夹后双击即可使用。
pause
