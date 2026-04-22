import pandas as pd
import numpy as np

class StrategyFactory:
    """量化策略工厂：包含多种经典策略"""
    
    @staticmethod
    def generate_signals(df: pd.DataFrame, strategy_name: str, params: dict) -> pd.DataFrame:
        """根据策略名称路由到对应的算法"""
        df = df.copy()
        df['trade_signal'] = 0 # 0: 持仓/观望, 1: 买入, -1: 卖出
        
        if strategy_name == "dual_ma":
            return StrategyFactory._dual_ma(df, params)
        elif strategy_name == "bollinger_bands":
            return StrategyFactory._bollinger_bands(df, params)
        elif strategy_name == "rsi_reversal":
            return StrategyFactory._rsi_reversal(df, params)
        else:
            raise ValueError(f"未知的策略名称: {strategy_name}")

    # ==========================================
    # 策略 1: 经典双均线交叉 (趋势跟随)
    # ==========================================
    @staticmethod
    def _dual_ma(df: pd.DataFrame, params: dict) -> pd.DataFrame:
        fast = params.get('fast_period', 5)
        slow = params.get('slow_period', 20)
        
        df['fast_ma'] = df['close'].rolling(window=fast).mean()
        df['slow_ma'] = df['close'].rolling(window=slow).mean()
        
        # 核心逻辑：今天快线上穿慢线，且昨天快线在慢线下方
        df.loc[(df['fast_ma'] > df['slow_ma']) & (df['fast_ma'].shift(1) <= df['slow_ma'].shift(1)), 'trade_signal'] = 1
        df.loc[(df['fast_ma'] < df['slow_ma']) & (df['fast_ma'].shift(1) >= df['slow_ma'].shift(1)), 'trade_signal'] = -1
        
        return df

    # ==========================================
    # 策略 2: 布林带均值回归 (震荡市收割机)
    # 逻辑：跌破下轨买入，突破上轨卖出
    # ==========================================
    @staticmethod
    def _bollinger_bands(df: pd.DataFrame, params: dict) -> pd.DataFrame:
        window = params.get('window', 20)
        std_dev = params.get('std_dev', 2.0)
        
        df['middle_band'] = df['close'].rolling(window=window).mean()
        df['std'] = df['close'].rolling(window=window).std()
        df['upper_band'] = df['middle_band'] + (df['std'] * std_dev)
        df['lower_band'] = df['middle_band'] - (df['std'] * std_dev)
        
        # 价格跌破下轨买入 (抄底)
        df.loc[df['close'] < df['lower_band'], 'trade_signal'] = 1
        # 价格突破上轨卖出 (逃顶)
        df.loc[df['close'] > df['upper_band'], 'trade_signal'] = -1
        
        return df

    # ==========================================
    # 策略 3: RSI 超买超卖 (动量反转)
    # 逻辑：RSI极度低迷时买入，极度狂热时卖出
    # ==========================================
    @staticmethod
    def _rsi_reversal(df: pd.DataFrame, params: dict) -> pd.DataFrame:
        window = params.get('window', 14)
        buy_threshold = params.get('buy_threshold', 30)   # 默认低于30超卖买入
        sell_threshold = params.get('sell_threshold', 70) # 默认高于70超买卖出
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        df.loc[(df['rsi'] < buy_threshold) & (df['rsi'].shift(1) >= buy_threshold), 'trade_signal'] = 1
        df.loc[(df['rsi'] > sell_threshold) & (df['rsi'].shift(1) <= sell_threshold), 'trade_signal'] = -1
        
        return df