# 边界情况与处理（触发时先查这张表）

| 情形 | 处理 |
|---|---|
| preflight 同构（评审者 effective model 等于起草记录的 selected/physical） | **fail-closed**：不进循环，输出部署指引；只有用户改完配置重新触发才继续 |
| `spec-reviewer` 未注册 / `{action:"models"}` 无法解析 | preflight 报错，给出 package.json 注册指引，不进循环 |
| `modelScope` 拒绝（preflight 或运行期） | 停循环，输出报错形态与当前 allow 实况，交用户处置 |
| 草稿头缺 `Drafted:` 行 | 询问起草模型；答「未知」则停在 preflight 前（门禁无法执行），不自动降级 |
| 用户用**自然语言**触发且会话里没有 issue 上下文 | 要求用户给出 issue 编号，不猜目录 |
| state 索引缺失 / 过期 / 与文件系统矛盾 | 按轮次文件**重建**（最大轮次号 + 是否含 `## 修订摘要` 段），回写 state 并在 issue 评论说明 |
| spec 的 hash 不匹配（child 复核不一致，或父回收时与派发时不一致） | 停下要求对齐，不审来历不明的版本 |
| 派发失败 / **超时** / 结构化输出缺失或不合 schema | 停循环 + 留痕 + 报错；不静默重派（防重复扣费），由用户决定重试 |
| 复核零发现 | 仍写轮次报告（五视角逐项「核对通过」）与收敛判定；不省留痕 |
| 到达**轮次上限**（默认 4）仍有真缺口 | 停止循环，如实交用户决定（继续 / 降级接受 / 改设计），不允许自动继续或假装收敛 |
| 用户要求跳过真缺口 | 允许，但必须在该轮修订摘要里记录「用户决定跳过」+ 理由 |
| 用户显式要求同模型**降级复核** | 停在派发前，输出定稿降级提示；仅在明确回复「降级复核」后，同会话按降级轮执行并在报告头标注 |
| 虚拟模型（`PI_MODEL` 是 router） | preflight 按 selected 保守比对；child run 的 model 与主会话 physical 事后记录；撞真身则 `Mode` 记 `cross-model (post-hoc same-physical)` 并按降级轮对待 |
| 报告 / state / 评论写入失败 | 停循环、报错、不重派 |
| 显式触发落在**已收敛** / 已批准状态 | 报告已收敛，进入 ⏸ 等用户确认设计，不重开轮次 |
| `{action:"models"}` 返回 `(unresolved)` | 视同无法判定异构，preflight fail-closed |
| `PI_SESSION_FILE` 未设置（ephemeral session） | 报告头 physical 记 `(unavailable, ephemeral session)`，本轮跳过撞真身判定 |
