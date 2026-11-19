# MoviePilot 插件仓库（liujuncdb）

MoviePilot V3 插件市场仓库。当前包含 **1** 个插件。

## 插件列表

| 插件 | 版本 | 说明 |
| --- | --- | --- |
| FFmpegStrm缩略图·中间帧魔改 | 2.1.0 | 按影片片长截取正中间一帧作为 STRM 缩略图 |

## 安装方式

在 MoviePilot 中打开「设置 → 插件市场」，添加本仓库：

```
liujuncdb/moviepilot-plugins
```

保存后进入「插件」页面，在市场的「全部插件」里搜索 `FFmpegStrm` 即可安装。之后本仓库发布新版本时，插件页会提示更新。

## 仓库结构

```
package.v3.json                     插件索引（版本、描述、更新历史）
icons/                              插件列表图标
plugins.v3/<插件id小写>/            插件源码目录
```

索引字段遵循 MoviePilot V3 规范：`name / description / labels / version / icon / author / level / release / system_version / history`，`version` 使用 PEP440 格式，且与插件内的 `plugin_version` 保持一致。

## 发布新版本

1. 修改 `plugins.v3/<id>/__init__.py` 中的 `plugin_version`
2. 同步修改 `package.v3.json` 中的 `version`，并在 `history` 顶部新增一条同版本号记录
3. 提交并推送，MoviePilot 下次检查更新时即可发现新版本
