#!/bin/zsh
cd "${0:A:h}" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  print '需要 Python 3。请安装后重新双击此文件。'
  read 'reply?按回车关闭…'
  exit 1
fi
python3 serve.py
if [[ $? -ne 0 ]]; then
  read 'reply?启动未成功，请查看上方提示。按回车关闭…'
fi
