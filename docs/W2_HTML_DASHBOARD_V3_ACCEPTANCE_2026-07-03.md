# W2 终端 Dashboard v3 重建 · 验收与部署报告（强制执行版）

出具：Claude ／ 2026-07-03 ／ 工作区基线：`47b9173`（A-RUNTIME-005）
性质：事故修复 + 重新交付。技术员必须按第 5、6 节完成 GitHub 同步与云端部署，缺一不算完成。

## 1. 事故还原（为什么"昨晚还在、今天回退"）

不是部署系统抽风，是流程漏洞：

1. 终端风格渲染器（v1→v3）此前只改在**服务器工作区**，从未 `git commit`，更未 push GitHub。
2. 我在事故现场核实：`git status` 干净、`report_generator.py` 回到 849 行旧白底版、仓库新增了 `ac82cdb`、`47b9173` 两个别的提交——说明技术员在做这两个提交前后执行过 `git checkout/reset/pull` 类操作，把未提交的渲染器改动清掉了。
3. 结论：**昨晚的页面来自未入库的工作区文件；今天任何一次从 git 重建都必然回退。** 版本库里从来就没有过新版。

## 2. 本次重建内容

已把 v3 终端渲染器完整重写回 `src/w2/reporting/report_generator.py`（当前工作区，等待技术员提交）：

- 对齐十列网格 + 列头：时间｜联赛｜对阵｜状态｜原因｜盘｜差｜ISC｜走势·参照｜as-of；数字列右对齐等宽、行斑马纹、窄屏自动收缩六列。
- 正式推荐置顶且组内 EV 降序；FORMAL 行 = 对齐主行 + 绿色决策条（推荐主张 + EV + 我们的盘/市场盘/差距/比分 top3 合并截断）。
- 重复元信息（状态整句/走势整句/数据三项/完整 as-of）收进每行悬停提示；"数据未齐"琥珀角标仅在赔率/首发/xG 任一未就绪时出现。
- 状态过滤 chips（带计数）、联赛下拉、球队搜索、三种排序；纯客户端显示过滤，零请求。
- 审计明细两张表（正式推荐表 / 非 FORMAL 判定表含 blocker 中文解释）保留于折叠区。
- 红线全保留：FORMAL 才显示方向/比分、禁词 guard 作用于整页、as-of 强制、确定性输出、页脚免责声明。
- **新增防回退水印**：`HTML_RENDERER_VERSION = "w2.html_dashboard.v3"`，同时写入 `<meta name="w2-renderer">` 与页脚。任何人打开页面或 curl 一下就能确认线上跑的是哪一版。

## 3. 版本指纹（验收对照物）

| 项 | 值 |
|---|---|
| 文件 | `src/w2/reporting/report_generator.py` |
| 行数 | 1095（旧版 849） |
| SHA256 | `bb605eea730a4611b67724404ee1cae39541658651a8d5fbb4ebf95a2524e5b4` |
| 渲染器标识 | `w2.html_dashboard.v3`（meta + 页脚） |
| diff 规模 | +345 / -99，单文件 |

提交前先核对：`sha256sum src/w2/reporting/report_generator.py` 必须等于上表值；不等说明文件又被动过，停下来查。

## 4. 本地验收（提交前）

```
pytest tests/unit/test_report_generator_output.py tests/unit/test_report_generator_cli.py \
       tests/unit/test_report_runner.py -q     # 必须全绿
pytest -q                                       # 全量回归
python scripts/generate_w2_report.py --url "http://<staging>/v1/dashboard?window=today" \
       --format html --output /tmp/w2_check.html
grep -c 'w2.html_dashboard.v3' /tmp/w2_check.html   # 期望 ≥2（meta+页脚）
```

页面人工检查五项：正式置顶且 EV 降序；数字成列对齐；非正式行悬停可见完整走势/数据/as-of；无正式推荐日不出现任何方向与比分；过滤/搜索/排序可用。

（说明：我已在隔离环境复刻六个测试场景全部通过——空日、50 场排序与 EV、无正式日、恶意队名转义、禁词拦截、text/markdown 路径不受影响。沙箱无法运行你们的 pytest，正式判定以上述命令为准。）

## 5. GitHub 同步（强制，事故根因的直接修复）

```
cd <repo>
git checkout -b fix/html-dashboard-v3-restore
git add src/w2/reporting/report_generator.py docs/W2_HTML_DASHBOARD_V3_ACCEPTANCE_2026-07-03.md
git commit -m "A-134C restore terminal dashboard v3 renderer with version watermark"
git push origin fix/html-dashboard-v3-restore
# 按你们流程合入主干分支并 push；合并后记录 merge SHA：______
```

同批建议补一个 pin 测试（防止再次无声回退，10 行）：

```python
# tests/unit/test_html_renderer_version.py
from w2.reporting.report_generator import HTML_RENDERER_VERSION, render_report

def test_html_renderer_version_pinned() -> None:
    assert HTML_RENDERER_VERSION == "w2.html_dashboard.v3"
    html = render_report(
        {"selected_football_day": "2026-06-30",
         "generated_at": "2026-06-30T23:40:00Z", "all": []},
        output_format="html",
    )
    assert 'name="w2-renderer" content="w2.html_dashboard.v3"' in html
```

有了这个测试，任何把渲染器退回旧版的提交都会直接挂 CI，而不是等你第二天看页面才发现。

## 6. 云端部署与部署后验证（强制）

```
# 1) 部署机上确认构建源就是刚合并的 SHA
git fetch && git rev-parse origin/<主干>        # 必须等于第 5 步的 merge SHA
# 2) 按你们现有流程重建/重启 api 与 runner
# 3) 重新生成当日页面
python scripts/run_w2_report_runner.py --base-url http://<prod-api> --format html --sink file
# 4) 三条硬验证，全过才算部署完成：
curl -s http://<prod>/v1/version | grep api_git_sha        # 等于 merge SHA
curl -s http://<prod>/reports/w2_day_$(date +%F).html | grep -c 'w2.html_dashboard.v3'   # ≥2
curl -s http://<prod>/reports/w2_day_$(date +%F).html | grep -c '方向未识别'             # 必须为 0
```

## 7. 防回退协议（今后必须遵守）

1. **禁止在服务器工作区手改代码后直接跑生产**——本次事故的全部成因。任何改动：分支 → commit → push → CI 绿 → 部署。
2. 部署脚本末尾固定加第 6 节三条 curl 验证，任何一条不过自动判定部署失败。
3. 页面水印制度保留：今后每次渲染器改版递增版本号（v4、v5…），改版必须同步更新 pin 测试。
4. 每日 runner 生成页后，值班检查页脚 renderer 版本与预期一致（一眼的事）。

## 8. 验收签字栏

| 项 | 负责人 | 完成 |
|---|---|---|
| 本地 pytest 全绿 + sha256 对上 | 技术员 | ☐ |
| GitHub 合入 merge SHA 记录 | 技术员 | ☐ |
| pin 测试已添加 | 技术员 | ☐ |
| 云端三条 curl 验证全过 | 技术员 | ☐ |
| 页面人工五项检查 | 老板/技术员 | ☐ |
