import os
import yaml
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.core.data_center import DataCenter
from backend.core.engine import BacktestEngine
from backend.core.strategy import StrategyFactory 

app = FastAPI(title="Quant Simulate System API")

# 配置 CORS，允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 实例化数据中心
dc = DataCenter()

def load_config():
    """加载 YAML 配置文件"""
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config.yaml"))
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def clean_nan(df: pd.DataFrame) -> list:
    """清理 DataFrame 中的 NaN 值，防止 JSON 序列化报错"""
    return df.fillna("").to_dict(orient="records")

@app.get("/api/summary", summary="获取大盘总览数据")
async def get_summary(start_date: str = "20240101", end_date: str = "20240201"):
    config = load_config()
    pool = config['stock_pool']
    
    results = []
    for ticker in pool:
        try:
            # 1. 抓取数据
            raw_data = dc.fetch_stock_data(ticker, start_date="20230101", end_date=end_date)
            
            df_signals = StrategyFactory.generate_signals(
                raw_data, 
                config['strategy']['name'], 
                config['strategy']['parameters']
            )
            
            # 2. 严格按时间切片
            mask = (df_signals['date'] >= pd.to_datetime(start_date)) & \
                   (df_signals['date'] <= pd.to_datetime(end_date))
            df_slice = df_signals.loc[mask].copy().reset_index(drop=True)
            
            if df_slice.empty:
                continue

            # 3. 运行新版引擎
            engine = BacktestEngine(
                initial_cash=config['account']['initial_cash'],
                commission_rate=config['account']['commission_rate'],
                tax_rate=config['account']['tax_rate']
            )
            res = engine.run(df_slice, ticker)
            meta = res['metadata']
            
            results.append({
                "ticker": ticker,
                "strategy": config['strategy']['name'],
                "final_equity": meta['final_equity'],
                "return_rate": meta['total_return'], 
                "trade_count": meta['trade_count']
            })
        except Exception as e:
            print(f"⚠️ 处理 {ticker} 失败: {e}")
            
    return {"status": "success", "data": results}


@app.get("/api/detail/{ticker}", summary="获取单票详细数据")
async def get_detail(ticker: str, start_date: str = "20240101", end_date: str = "20240131"):
    config = load_config()
    
    try:
        raw_data = dc.fetch_stock_data(ticker, start_date="20230101", end_date=end_date)
        
        df_signals = StrategyFactory.generate_signals(
            raw_data, 
            config['strategy']['name'], 
            config['strategy']['parameters']
        )
        
        mask = (df_signals['date'] >= pd.to_datetime(start_date)) & \
               (df_signals['date'] <= pd.to_datetime(end_date))
        df_slice = df_signals.loc[mask].copy().reset_index(drop=True)
        
        if df_slice.empty:
            raise ValueError("该时间区间内没有交易数据")

        engine = BacktestEngine(
            initial_cash=config['account']['initial_cash'],
            commission_rate=config['account']['commission_rate'],
            tax_rate=config['account']['tax_rate']
        )
        res = engine.run(df_slice, ticker)
        
        res['data']['date'] = res['data']['date'].dt.strftime('%Y-%m-%d')
        
        return {
            "status": "success",
            "metadata": res['metadata'], 
            "klines": clean_nan(res['data']), 
            "logs": res['logs']
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))