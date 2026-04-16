# OBCX Plugin Registry

## 提交插件

1. Fork 此仓库
2. 在 `plugins/` 下创建 `<插件名>.toml`：
   ```toml
   [source]
   github = "your-username/obcx-plugin-xxx"
   ```
3. 提交 PR

你的插件仓库根目录需要有 `plugin.toml`，格式参考 [plugin_template](https://github.com/vollate/OBCX/tree/main/examples/plugin_template/plugin.toml)。
