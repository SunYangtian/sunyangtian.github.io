# 本地面试展示

中文面试网页，包含 9 个可见章节（个人介绍与教育背景合并）。使用本地 Reveal.js 5.2.1，日常运行无需联网、安装 npm 包或构建。

## 启动与停止

双击 **启动展示.command**。终端会启动服务并在默认浏览器打开 `http://127.0.0.1:8765/`。保留该终端窗口，结束时按 **Control+C**。关闭浏览器不会停止服务。

也可以在此目录运行：

```sh
python3 serve.py
```

仅绑定本机 `127.0.0.1`。如果端口被其他程序占用，运行 `python3 serve.py --port 8766`。重复启动相同内容时会直接打开已运行的展示。

请使用本地网址打开，不能直接双击 `index.html`，因为浏览器不允许从本地文件读取独立 JSON 内容。

## 展示操作

- **左右方向键 / 空格**：翻页。也可点击底部上一页、下一页。
- **目录**：跳转章节。演示模式按 **Esc** 可打开或关闭 Reveal.js 总览；对话框打开时 Esc 关闭对话框。
- **全屏**：进入或退出全屏。浏览器不支持时使用浏览器自带全屏菜单。
- **备注**：在当前页面查看讲解备注与来源。点击“打开独立演讲者窗口”，显示当前页、下一页和计时；需要允许本站弹窗。演示模式也可按 **S** 直接打开。
- **阅读模式**：切换为连续滚动；手机默认采用阅读模式。切回演示模式会保留当前章节。
- **离线**：主页面、照片、动画及框架均在本地。论文、邮箱和项目网站链接需要相应网络或应用。

分享屏幕时建议仅共享展示标签页，不共享备注窗口。静态文件中的备注并非访问受限数据；将来公开发布前可自行删除不希望公开的 notes 内容。

## 修改内容

打开 **content.json**，保存后刷新浏览器即可。该文件使用标准 JSON：键名与文字必须使用英文双引号，末尾不要多写逗号；编辑器可使用 VS Code。格式不正确时，页面会显示具体错误。

顶层 `name`、`email`、`homepage`、`date` 控制个人信息。`chapters` 中每个对象代表一个章节：

| 字段 | 用途 |
|---|---|
| `id` | 唯一章节标识，小写英文字母、数字、连字符，以字母开头；用于网址定位 |
| `layout` | 使用的布局，见下表 |
| `title` | 章节标题与目录标题 |
| `visible` | 设为 `false` 隐藏，不必删除 |
| `eyebrow` | 标题上方小字 |
| `notes` | 演讲备注，用 `\n` 表示换行 |
| `sources` | 来源链接数组，在备注中显示 |

**调整顺序**：移动 `chapters` 数组中的整个章节对象。页码和目录会自动更新。复制章节时必须给出新的 `id`。至少保留一个可见章节。

| 布局 | 内容字段 |
|---|---|
| `cover` | `subtitle`、`affiliation`、`description`、`intent`、`portrait`；可选 `educationId` 引用合并展示的教育章节 |
| `timeline` | `items`，每条包含 `date`、`title`、`role`、`description`；可选 `footer` |
| `project` | `subtitle`、`venue`、`authorship`、`blocks`、`media`、`links`；可选 `result`、`repository` |
| `comparison` | `items`，每项含 `title`、`meta`、`description`、`media`、`url`；可选 `repository` |
| `publications` | `columns`、`rows`、`footer`；可选 `repositories`、`extraProjects`；每行格数须等于列数 |
| `expertise` | `items`，每条含 `title`、`description`、`evidence`；可选 `footer` |
| `outlook` | `items`，每条含 `title`、`description`；`closing` 为结束语 |

例如，把某项目的一段文字改为：

```json
{"label": "方法", "text": "这里填写新的方法介绍。"}
```

幻灯片具有固定画布。每个项目建议保留 3 段短文，每段约 25–55 字；内容过多时拆成新章节或放入备注。移动端阅读会自动纵向排版。

## 替换图片或视频

把素材放入 **assets/**，修改对应 `media.src`。使用相对路径，避免 `/Users/...` 绝对路径。文件名建议使用英文及连字符。

图片和 GIF：

```json
{
  "type": "image",
  "src": "assets/mira-scene.gif",
  "poster": "assets/mira-scene.png",
  "alt": "单图重建三维场景结果",
  "caption": "单图输入与三维场景重建"
}
```

本地视频建议使用 **H.264 编码的 MP4**：

```json
{
  "type": "video",
  "src": "assets/demo.mp4",
  "poster": "assets/demo-poster.png",
  "alt": "项目视频演示",
  "caption": "实验结果"
}
```

视频显示播放控制，默认静音、循环，切离所在幻灯片时暂停。`poster` 用作视频封面和 PDF 静态画面，请为动画或视频保留一张 PNG/JPG。系统启用“减少动态效果”时，GIF 使用静态封面。

## 修改外观

修改 **theme.css** 开头的变量即可统一调整主题，例如 `--blue`、`--ink`、`--muted`、`--title-size`、`--body-size`。所有文字和表格均为 HTML 内容。

## 导出 PDF

在 Chrome 或 Edge 打开 `http://127.0.0.1:8765/?print-pdf`。等待素材加载后打印，选择“另存为 PDF”，关闭页眉页脚，开启背景图形，页边距设为无。每章一页，动画和视频使用静态封面，演讲备注不打印。

先检查预览页数与内容再保存。PDF 是静态备用材料，无法保留动画或网页交互。普通阅读页面打印不作为正式导出方式。

## 以后放到个人主页

将 `index.html`、`app.js`、`theme.css`、`content.json`、`assets/`、`vendor/` 一起复制到网站的 `interview/` 目录，再在主页增加指向 `interview/` 的链接。网页无后台或数据库。Python 服务和启动脚本仅用于本地，不是线上依赖。

## 内容来源与许可证

内容基于 2026 年 10 月的本地面试 PPT 和个人主页。VAST 经历采用本地最新修改。论文状态保留预印本标注，共同一作身份在项目和论文表格中统一说明。Google Scholar 引用数与 GitHub stars 为 2026-10-08 从 Scholar 个人页及 GitHub 官方仓库 API 采集的本地快照；页面标注采集日期，不依赖联网刷新。3DGSR 暂未确认官方仓库，明确标注而不填入推测数据。

照片与研究动画来自 https://sunyangtian.github.io/，使用于本人研究展示。项目具体来源保存在 content.json。Reveal.js 许可证随框架保存在 vendor/reveal/LICENSE。

## 引用数与 GitHub stars

首页合并个人介绍、教育背景和产业经历。原 `education`、`experience` 章节保留数据，设为 `visible: false`，由首页 `educationId`、`experienceId` 引用；编辑这两个章节仍会更新首页内容。

- `scholar`：`url` 为 Scholar 主页，`citations` 为动态请求失败时使用的本地后备值。
- `repositories`：按项目键保存官方仓库 `name`、`url`、`stars`；`stars` 是动态请求失败时使用的本地后备值。
- 本地服务的 `/metrics.json` 每次页面加载时读取 Google Scholar 和 GitHub API，网页随后更新数字；网络不可用或 API 限流时自动使用 `content.json` 中的后备值。
- 项目章节及对比项目的 `repository` 引用对应项目键。
- 代表论文的 `repositories` 与 `rows` 一一对应，自动增加 stars 列；少于 100 stars 的论文不会列出；`extraProjects` 展示其他核心贡献。

点击数字可打开来源。手机端论文表格支持横向滚动。
