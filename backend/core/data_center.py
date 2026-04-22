import os
import time
import random  # 新增：引入随机数模块
import glob
import pandas as pd
import akshare as ak
from datetime import datetime

class DataCenter:
    """
    量化系统的数据神经中枢
    负责调用 akshare 获取 A 股历史数据，并进行本地高速缓存
    """
    def __init__(self, cache_dir: str = "data/cache"):
        self.base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
        self.cache_dir = os.path.join(self.base_path, cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self.columns_map = {
            "日期": "date", "开盘": "open", "收盘": "close", 
            "最高": "high", "最低": "low", "成交量": "volume", 
            "成交额": "amount", "振幅": "amplitude", "涨跌幅": "pct_change", 
            "涨跌额": "change_amount", "换手率": "turnover"
        }

    def _clean_symbol(self, symbol: str) -> str:
        if symbol.startswith(("sh", "sz")):
            return symbol[2:]
        return symbol

    def fetch_stock_data(self, 
                         symbol: str, 
                         start_date: str = "20240101", 
                         end_date: str = "20260421", 
                         force_update: bool = False) -> pd.DataFrame:
        
        # 1. 智能模糊匹配：查找本地是否包含该股票代码的任何 parquet 文件
        search_pattern = os.path.join(self.cache_dir, f"{symbol}_*.parquet")
        existing_caches = glob.glob(search_pattern)

        # 如果找到了缓存文件，且没有强制要求更新
        if not force_update and existing_caches:
            # 默认读取找到的第一个该股票的缓存文件
            cache_file = existing_caches[0]
            print(f"📦 [DataCenter] 命中本地宽泛缓存: {os.path.basename(cache_file)}")
            
            # 读取全量本地数据
            df = pd.read_parquet(cache_file)
            
            # 在内存中进行时间切片，只切出引擎当前需要的日期段返回
            mask = (df['date'] >= pd.to_datetime(start_date)) & (df['date'] <= pd.to_datetime(end_date))
            return df.loc[mask].copy().reset_index(drop=True)

        # 2. 如果本地彻底没有这只股票，再走网络下载逻辑
        clean_code = self._clean_symbol(symbol)
        print(f"🌐 [DataCenter] 正在从东财下载新数据: {symbol}...")
        
        cache_file = os.path.join(self.cache_dir, f"{symbol}_{start_date}_{end_date}.parquet")
        max_retries = 5  
        df = pd.DataFrame()
        
        for attempt in range(max_retries):
            try:
                df = ak.stock_zh_a_hist(
                    symbol=clean_code, 
                    period="daily", 
                    start_date=start_date, 
                    end_date=end_date, 
                    adjust="qfq"
                )
                time.sleep(random.uniform(2.5, 5.0)) 
                break 
                
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(1.0, 3.0)
                    print(f"⚠️ 触发防爬限制。等待 {wait_time:.2f} 秒后进行第 {attempt + 1} 次重试...")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(f"❌ 下载 {symbol} 失败，已达最大重试次数。错误: {e}")

        if df.empty:
            raise ValueError(f"⚠️ {symbol} 返回数据为空，可能退市或停牌。")

        df.rename(columns=self.columns_map, inplace=True)
        df['date'] = pd.to_datetime(df['date'])
        df.sort_values(by='date', ascending=True, inplace=True)
        df.reset_index(drop=True, inplace=True)

        df.to_parquet(cache_file, index=False)
        print(f"✅ [DataCenter] 数据下载并缓存成功: {symbol}")

        return df