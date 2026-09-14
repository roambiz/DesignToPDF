COMPANY = "懒研科技"
SITE = "lazysci.com"
SITE_URL = "https://lazysci.com"
VERSION = "1.2.1"
APP_NAME = "设计底稿导出"
COPYRIGHT = "© lazysci.com 懒研科技"

INFO_HTML = """
<style>
  body {
    font-family: 'Microsoft YaHei', sans-serif;
    color: #1f2430;
    line-height: 1.7;
    margin: 0;
    padding: 4px 6px 8px;
  }
  h1 {
    font-size: 18px;
    font-weight: 650;
    margin: 0 0 14px;
  }
  h2 {
    font-size: 13px;
    font-weight: 650;
    margin: 18px 0 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid #e5e7eb;
  }
  p { margin: 0 0 10px; }
  ul, ol { margin: 0 0 12px; padding-left: 1.2em; }
  li { margin: 0 0 6px; }
  code {
    background: #f3f4f6;
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 12px;
  }
</style>
<h1>使用说明</h1>

<h2>使用场景</h2>
<p>给装不了 Photoshop / Illustrator 的电脑用。把设计源文件转成 PDF 或图片，方便快速翻看底稿，或发给同事、客户预览。</p>
<ul>
  <li>旧电脑打不开 AI / PSD，只需要看画面</li>
  <li>多页文件要按页拆开，逐页浏览或分发</li>
  <li>批量把设计源文件转成统一格式归档</li>
</ul>

<h2>操作步骤</h2>
<ol>
  <li>把 <code>.ai</code>、<code>.psd</code>、整个文件夹或 zip 拖进窗口。从压缩软件预览窗口里拖不如先解压到桌面稳</li>
  <li>选择输出文件夹</li>
  <li>选择导出 PDF、PNG 或 JPEG</li>
  <li>多页文件若要一页一个文件，勾选「按页分割」</li>
  <li>按需要勾选「覆盖已有文件」「完成后打开」「记住设置」</li>
  <li>点「导出」。加入文件、进度和结果都写在下方日志里</li>
</ol>

<h2>按页分割</h2>
<p>PDF 与图片都支持。勾选后，多页会拆成 <code>稿件.pdf</code> / <code>稿件_2.pdf</code>，或对应的 PNG。不勾选时，PDF 保留全部页；图片只导出第 1 页。</p>

<h2>覆盖已有文件</h2>
<p>默认不勾选。输出文件夹里已有同名结果时会跳过，避免盖掉上次的文件。勾选后直接覆盖同名 PDF / 图片。</p>

<h2>完成后打开</h2>
<p>勾选后，全部导出成功会自动打开输出文件夹。中途点「停止」，或有文件失败，则不会自动打开。也可以随时点「打开输出文件夹」。</p>

<h2>记住设置</h2>
<p>默认勾选。下次打开会保留输出文件夹、导出格式和勾选。不勾选则不记住，适合公用电脑。</p>

<h2>支持格式</h2>
<p>AI、EPS、PS、PSD、SVG、PDF、INDD、CDR、Sketch、XD、Affinity，以及 PNG / JPG / TIFF 等位图。</p>

<h2>补充说明</h2>
<p>导出的是方便查看的预览底稿，不能当作源文件继续修改。图层、字体和特效都不会完整保留。</p>
<p>这是单个程序，适用于 64 位 Windows 7 SP1 至 Windows 11。32 位系统不支持。先保存到桌面再双击打开，不要在微信聊天里直接点开。若直接从聊天拖入文件，输出会放到桌面「导出结果」，避免微信清理后找不到。也可以拖入 zip，程序会展开里面的设计文件；rar / 7z 请先解压。从压缩软件预览窗口或网盘未下完的位置拖入时，会尽量复制到本地再处理。单文件第一次打开会先解压再进窗口，可能稍慢；窗口出现后底部会显示「准备中」，日志提示加载完成后再拖入文件。</p>
<p>一次导出结束后，已经完成、跳过或失败的文件会自动移出队列。再拖入新文件时，只会处理新加入的文件。「完成后打开」始终打开本次选择的输出文件夹。</p>
<p>部分 AI 文件若本机安装了 Adobe Illustrator，可尝试更完整的导出；未安装时会自动改用内嵌预览图。</p>
"""

