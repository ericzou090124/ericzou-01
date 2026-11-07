# 全版本可用性审计报告

> 由 `tools/version_audit.py` 自动生成。逐个 tag 检出到隔离临时目录，
> 执行归档完整性 / 配置解析 / 全量编译 / 模块导入 / 核心链路 / 群文件分类 / 微信适配器 / 路由 / 前端语法 / 自带自测。
> 检测过程使用独立 `state/`，**不读写工作区真实资料**。
> 本报告是**生成时刻的快照**，覆盖当时已存在的全部 tag；之后新发布的版本请重新运行 `python tools/version_audit.py`。

## 汇总

- 审计版本数：**26**
- 通过：**22**
- 已知历史问题（已提供补丁标签）：**4**
- 未修复失败：**0**

## 结论与修复

全量审计发现 `v1.3.0` ~ `v1.6.0` 四个历史版本的 `ai.answer("")` 会在变量 `f` 定义前引用 `scope=f`，
抛 `NameError`（空查询即崩溃）。该缺陷已在 **v1.7.0** 主线修复。

为兼顾「历史可原样回溯」与「回退版本仍可用」，**不改写、不移动任何原 tag**，
而是用 `tools/fix_legacy_tag.py` 基于每个受影响 tag 生成只含最小修复的提交，
并打上补丁标签 `vX.Y.Z-p1`。下表 `KNOWN` 行表示原 tag 如实保留缺陷、补丁标签已通过全部检测；
需要回退到该系列版本时请检出 `-p1` 标签。

| 原 tag | 状态 | 可用替代 |
| --- | --- | --- |
| `v1.3.0` | ⚠️ 已知缺陷（空问题 NameError） | `v1.3.0-p1` ✅ |
| `v1.4.0` | ⚠️ 已知缺陷（空问题 NameError） | `v1.4.0-p1` ✅ |
| `v1.5.0` | ⚠️ 已知缺陷（空问题 NameError） | `v1.5.0-p1` ✅ |
| `v1.6.0` | ⚠️ 已知缺陷（空问题 NameError） | `v1.6.0-p1` ✅ |

## 逐版本检测结果

| 版本 | 结果 | Commit | .py | 关键文件 | 配置 | 编译 | 导入 | 核心链路 | 分类/微信 | 路由 | 前端 | 自带自测 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `v1.0.0` | ✅ PASS | `ce184cfdf8` | 14 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `v1.0.1` | ✅ PASS | `e7b0724baa` | 14 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `v1.1.0` | ✅ PASS | `5559d41ae1` | 16 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `v1.2.0` | ✅ PASS | `4f5f38b182` | 16 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `v1.2.1` | ✅ PASS | `69a31a607e` | 18 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `v1.2.2` | ✅ PASS | `c455952dee` | 20 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `v1.2.3` | ✅ PASS | `f0d57355da` | 21 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `v1.3.0` | ⚠️ KNOWN（见补丁） | `01c5fb8aae` | 21 | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | — |
| `v1.3.0-p1` | ✅ PASS | `def9910907` | 21 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `v1.4.0` | ⚠️ KNOWN（见补丁） | `b43aef9757` | 21 | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | — |
| `v1.4.0-p1` | ✅ PASS | `7209444f11` | 21 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `v1.5.0` | ⚠️ KNOWN（见补丁） | `d3c078e758` | 22 | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | — |
| `v1.5.0-p1` | ✅ PASS | `25ee274f12` | 22 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `v1.6.0` | ⚠️ KNOWN（见补丁） | `4d455a7404` | 23 | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ |
| `v1.6.0-p1` | ✅ PASS | `d866d9066e` | 23 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `v1.7.0` | ✅ PASS | `4166e1562c` | 23 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `v1.8.0` | ✅ PASS | `28b8f25674` | 23 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `v1.9.0` | ✅ PASS | `47c806c137` | 23 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `v2.0.0` | ✅ PASS | `99c302fabb` | 23 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `v2.1.0` | ✅ PASS | `0aa23ba4f1` | 24 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `v2.2.0` | ✅ PASS | `1bced18424` | 24 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `v2.3.0` | ✅ PASS | `280f72cec9` | 24 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `v2.4.0` | ✅ PASS | `f9505bf490` | 25 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `v2.5.0` | ✅ PASS | `1b75404373` | 25 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `v2.6.0` | ✅ PASS | `72c232f449` | 25 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `v2.7.0` | ✅ PASS | `760192ab2c` | 25 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

## 明细与异常

### `v1.0.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=真题试卷 hits=1 mode=catalog`
- 功能探测：`FEATURES_OK wcf=absent named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,qq,vault,wechat
- 全部检测项通过，无异常。

### `v1.0.1` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=真题试卷 hits=1 mode=catalog`
- 功能探测：`FEATURES_OK wcf=absent named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,qq,vault,wechat
- 全部检测项通过，无异常。

### `v1.1.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=真题试卷 hits=1 mode=catalog`
- 功能探测：`FEATURES_OK wcf=absent named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,qq,qqlogin,vault,wechat
- 全部检测项通过，无异常。

### `v1.2.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=真题试卷 hits=1 mode=catalog`
- 功能探测：`FEATURES_OK wcf=absent named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,qq,qqlogin,vault,wechat
- 全部检测项通过，无异常。

### `v1.2.1` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=真题试卷 hits=1 mode=catalog`
- 功能探测：`FEATURES_OK wcf=absent named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,qq,qqlogin,vault,wechat
- 全部检测项通过，无异常。

### `v1.2.2` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=真题试卷 hits=1 mode=catalog`
- 功能探测：`FEATURES_OK wcf=absent named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat
- 全部检测项通过，无异常。

### `v1.2.3` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=真题试卷 hits=1 mode=catalog`
- 功能探测：`FEATURES_OK wcf=absent named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat
- 全部检测项通过，无异常。

### `v1.3.0` — KNOWN

- 功能探测：`FEATURES_OK wcf=absent named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat
- ✅ 已提供可用补丁标签：`v1.3.0-p1`（全项通过）；原 tag 保持不动以便历史回溯
- ❌ 核心链路失败: Traceback (most recent call last):
  File "<string>", line 30, in <module>
    r0 = ai.answer("", cat)
  File "C:\Users\ERICZOU\AppData\Local\Temp\rm_audit_v1_3_0_4qob_w_j\lib\ai.py", line 164, in answer
    return {"answer": "请输入问题。", "found": False, "sources": [], "mode": "none", "scope": f, "took_ms": 0}
                                                                                           

### `v1.3.0-p1` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=absent named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat
- 全部检测项通过，无异常。

### `v1.4.0` — KNOWN

- 功能探测：`FEATURES_OK wcf=absent named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat
- ✅ 已提供可用补丁标签：`v1.4.0-p1`（全项通过）；原 tag 保持不动以便历史回溯
- ❌ 核心链路失败: Traceback (most recent call last):
  File "<string>", line 30, in <module>
    r0 = ai.answer("", cat)
  File "C:\Users\ERICZOU\AppData\Local\Temp\rm_audit_v1_4_0_skyqwz5a\lib\ai.py", line 164, in answer
    return {"answer": "请输入问题。", "found": False, "sources": [], "mode": "none", "scope": f, "took_ms": 0}
                                                                                           

### `v1.4.0-p1` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=absent named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat
- 全部检测项通过，无异常。

### `v1.5.0` — KNOWN

- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- ✅ 已提供可用补丁标签：`v1.5.0-p1`（全项通过）；原 tag 保持不动以便历史回溯
- ❌ 核心链路失败: Traceback (most recent call last):
  File "<string>", line 30, in <module>
    r0 = ai.answer("", cat)
  File "C:\Users\ERICZOU\AppData\Local\Temp\rm_audit_v1_5_0_vuea2j9v\lib\ai.py", line 164, in answer
    return {"answer": "请输入问题。", "found": False, "sources": [], "mode": "none", "scope": f, "took_ms": 0}
                                                                                           

### `v1.5.0-p1` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 全部检测项通过，无异常。

### `v1.6.0` — KNOWN

- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 自带自测末行：ALL PASS
- ✅ 已提供可用补丁标签：`v1.6.0-p1`（全项通过）；原 tag 保持不动以便历史回溯
- ❌ 核心链路失败: Traceback (most recent call last):
  File "<string>", line 30, in <module>
    r0 = ai.answer("", cat)
  File "C:\Users\ERICZOU\AppData\Local\Temp\rm_audit_v1_6_0_5d6wpgrc\lib\ai.py", line 164, in answer
    return {"answer": "请输入问题。", "found": False, "sources": [], "mode": "none", "scope": f, "took_ms": 0}
                                                                                           

### `v1.6.0-p1` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 自带自测末行：ALL PASS
- 全部检测项通过，无异常。

### `v1.7.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 自带自测末行：ALL PASS
- 全部检测项通过，无异常。

### `v1.8.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 自带自测末行：ALL PASS
- 全部检测项通过，无异常。

### `v1.9.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 自带自测末行：ALL PASS
- 全部检测项通过，无异常。

### `v2.0.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 自带自测末行：ALL PASS
- 全部检测项通过，无异常。

### `v2.1.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 自带自测末行：ALL PASS
- 全部检测项通过，无异常。

### `v2.2.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 自带自测末行：ALL PASS
- 全部检测项通过，无异常。

### `v2.3.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 自带自测末行：ALL PASS
- 全部检测项通过，无异常。

### `v2.4.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,config_validate,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 自带自测末行：ALL PASS
- 全部检测项通过，无异常。

### `v2.5.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,config_validate,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 自带自测末行：ALL PASS
- 全部检测项通过，无异常。

### `v2.6.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,config_validate,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 自带自测末行：ALL PASS
- 全部检测项通过，无异常。

### `v2.7.0` — PASS

- 核心链路：`CORE_OK domain=考试与复习 subject=高等数学 kind=试卷与解析 hits=1 mode=none`
- 功能探测：`FEATURES_OK wcf=ok named=6/6`
- 导入模块：ai,catalog,classify,config,config_validate,download,extract,index,llm,napcat_launch,qq,qqlogin,vault,wechat,wechat_wcf
- 自带自测末行：ALL PASS
- 全部检测项通过，无异常。

