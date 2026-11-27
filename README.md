# 茶庄园品控溯源系统

制茶师、品控员和庄园主协作管理茶园地块、制茶工序与溯源链条，确保每一批次茶叶从鲜叶到成品全程可追溯。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/routers/trace_activation_routes.py  溯源码启用总单/印版更正/包装领用接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 茶园地块 | `tea_garden` | 地块 | 海拔高度、种植面积、茶树品种 |
| 鲜叶采摘 | `picking` | 采摘批次 | 采摘日期、采摘人员、芽叶标准 |
| 萎凋工序 | `withering` | 萎凋记录 | 摊晾厚度、翻动次数、失水率 |
| 杀青工序 | `fixing` | 杀青记录 | 锅温设定、杀青时长、投叶量 |
| 揉捻工序 | `rolling` | 揉捻记录 | 压力档位、揉捻时长、成条率 |
| 发酵工序 | `fermentation` | 发酵记录 | 环境温度、环境湿度、堆高尺寸 |
| 干燥工序 | `drying` | 干燥记录 | 起始温度、终止温度、干燥时长 |
| 精制分级 | `grading` | 分级结果 | 筛号规格、碎末比例、等级判定 |
| 拼配配方 | `blending` | 拼配批次 | 原料比例、拼配日期、口感评分 |
| 包装规格 | `packing` | 包装批 | 包装形式、净含量、标签文案 |
| 仓储养护 | `storage` | 养护记录 | 入库温度、入库湿度、陈化周期 |
| 检测报告 | `testing` | 检测报告 | 农残项目、检测机构、报告编号 |
| 认证资质 | `certification` | 资质证书 | 证书类型、发证机构、有效期至 |
| 溯源码段 | `trace_code` | 码段 | 起始码号、结束码号、激活日期 |
| 发运交接 | `shipment` | 发运单 | 收货方、物流单号、发运日期 |
| 样品留样 | `sample` | 留样记录 | 留样编号、取样节点、样品形态 |
| 不合格处置 | `defect` | 缺陷记录 | 缺陷类型、发现节点、处置方式 |
| 内审巡查 | `audit` | 巡查记录 | 巡查日期、巡查要点、整改期限 |

### 溯源码启用总单

码段工作台使用独立页面 `/trace-activation`，后端接口前缀为 `/api/trace-activation`。

- 一张启用总单可一次提交多套印版，但系统逐项受理，不提供多选印版批量启用。
- 印版状态分为 `已受理`、`整组等核验`、`独立错误`。上传资料失败的印版不会生成可用码段，也不能被包装消耗。
- 号码与已激活码段或其他已受理印版重叠时，只把该印版判为独立错误，不影响同总单其他印版。
- 只有 `已受理` 印版可由包装工位领取；每个印版最多对应一次真实包装批使用，重复领取会被拒绝。
- 总单支持从原未办结印版继续提交；更正印版时保留前一份处理原因，并分别记录首次与修正后实际使用范围。

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

领域：应用开发
子方向：web前端/全栈开发
