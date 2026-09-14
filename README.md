# 设计底稿导出（DesignToPDF）

当前版本 **1.2.1**。把 AI、PSD、PDF 等设计源文件转成 PDF / PNG / JPEG **预览底稿**，给装不了 Photoshop、Illustrator 的电脑用来看稿、传阅。

导出的是方便查看的画面，不是可继续编辑的源文件。

适用于 **64 位 Windows 7 SP1 至 Windows 11**。32 位系统不支持。

由 [lazysci.com 懒研科技](https://lazysci.com) 制作。

---

## 懒研科技

[lazysci.com](https://lazysci.com) 是懒研科技的站点。我们做给真实工作场景用的小工具：旧电脑、微信传文件、不会装运行库的同事，也要能打开就用。

这个仓库是其中一款桌面工具。问题记录见 [开发日志](开发日志.md)。

---

## 给同事怎么用

微信里请发压缩包 `设计底稿导出-1.2.1.zip`，不要直接发 exe。手机微信对 exe 只显示问号，也更容易被拦截。

1. 把压缩包保存到桌面并解压
2. 双击 `设计底稿导出.exe`（不要在微信里直接打开）
3. 把设计文件、文件夹或 zip 拖进窗口，选输出文件夹，点「导出」。从压缩软件预览窗口拖入不如先解压到桌面稳。

支持：AI、EPS、PS、PSD、SVG、PDF、INDD、CDR、Sketch、XD、Affinity，以及 PNG / JPG / TIFF 等位图。多页可按页拆开。

单文件要先解压，窗口会尽快出现；底部进度条显示「准备中」，日志提示加载完成后再拖文件。

---

## 从源码运行

发布用的通用包必须用 **Python 3.8 + PySide2**（`.venv38`），不要用本机较新的 Python / PySide6 打给 Win7。

```bat
打包成EXE.bat
```

完成后：`发布\设计底稿导出-1.2.1\设计底稿导出.exe`

本机开发（Win10+，可用 PySide6）：

```bat
启动转换.bat
```

或：

```text
python -m pip install -r requirements.txt
python app.py
```

命令行：

```text
python app.py --cli --help
```

---

## 仓库里有什么

| 文件 | 说明 |
| --- | --- |
| `app.py` | 窗口 |
| `convert.py` | 转换 |
| `source_scan.py` | 扫文件、zip / 预览拖入、临时路径防护 |
| `qt_compat.py` | PySide6 / PySide2 兼容 |
| `brand.py` | 名称、版本、使用说明 |
| `DesignToPDF.spec` | PyInstaller 单文件打包 |
| `requirements-win7.txt` | Win7–Win11 发布依赖 |
| `开发日志.md` | 做到 1.2.0 为止遇到的问题 |

不提交虚拟环境、`build`、`dist` 和打好的 `发布` 目录。

---

Copyright © 2026 [lazysci.com](https://lazysci.com) 懒研科技
