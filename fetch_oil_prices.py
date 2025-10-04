#!/usr/bin/env python3
"""
中国油价数据抓取脚本 - 根目录版本
"""

import requests
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
import time
import re

class ChinaOilPriceAPI:
    def __init__(self):
        # 从配置文件加载省份数据
        with open('provinces.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.provinces = config['provinces']
        
    def fetch_all_prices(self):
        """抓取所有省份油价数据"""
        all_data = {}
        success_count = 0
        
        for province_name, province_code in self.provinces.items():
            print(f"🔄 正在抓取 {province_name} 油价数据...")
            
            try:
                province_data = self.fetch_province_price(province_name, province_code)
                all_data[province_name] = province_data
                
                if province_data['status'] == 'success':
                    success_count += 1
                    print(f"✅ {province_name} 数据获取成功")
                else:
                    print(f"❌ {province_name} 数据获取失败: {province_data['error']['message']}")
                    
            except Exception as e:
                error_data = self._create_error_data(province_name, province_code, f"抓取异常: {str(e)}")
                all_data[province_name] = error_data
                print(f"❌ {province_name} 抓取异常: {str(e)}")
            
            # 礼貌性延迟，避免请求过快
            time.sleep(1)
        
        return self._create_final_output(all_data, success_count)
    
    def fetch_province_price(self, province_name, province_code):
        """抓取单个省份油价数据"""
        try:
            url = f'http://www.qiyoujiage.com/{province_code}.shtml'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                return self._create_error_data(province_name, province_code, f"HTTP状态码: {response.status_code}")
            
            # 解析油价数据
            prices = self.parse_oil_prices(response.text)
            
            if not prices:
                return self._create_error_data(province_name, province_code, "无法解析油价数据")
            
            # 获取调整信息
            adjustment_info = self.parse_adjustment_info(response.text)
            
            return {
                "status": "success",
                "name": province_name,
                "code": province_code,
                "prices": prices,
                "unit": "元/升",
                "update_time": datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00'),
                "next_adjustment": adjustment_info.get('next_adjustment'),
                "trend": adjustment_info.get('trend')
            }
            
        except requests.exceptions.Timeout:
            return self._create_error_data(province_name, province_code, "请求超时")
        except requests.exceptions.RequestException as e:
            return self._create_error_data(province_name, province_code, f"网络请求失败: {str(e)}")
        except Exception as e:
            return self._create_error_data(province_name, province_code, f"解析异常: {str(e)}")
    
    def parse_oil_prices(self, html):
        """解析油价数据"""
        try:
            prices = {}
            
            # 方法1: 正则匹配各种油价格式
            patterns = {
                '92': [r'92#.*?([\d.]+)元', r'92.*?([\d.]+)元', r'92号.*?([\d.]+)元'],
                '95': [r'95#.*?([\d.]+)元', r'95.*?([\d.]+)元', r'95号.*?([\d.]+)元'],
                '98': [r'98#.*?([\d.]+)元', r'98.*?([\d.]+)元', r'98号.*?([\d.]+)元'],
                '0': [r'0#.*?([\d.]+)元', r'柴油.*?([\d.]+)元', r'0号.*?([\d.]+)元']
            }
            
            for oil_type, pattern_list in patterns.items():
                for pattern in pattern_list:
                    match = re.search(pattern, html)
                    if match:
                        try:
                            prices[oil_type] = float(match.group(1))
                            break  # 找到一个匹配就跳出
                        except ValueError:
                            continue
            
            # 如果找到了至少一种油价，就认为成功
            return prices if prices else None
            
        except Exception as e:
            print(f"解析价格异常: {str(e)}")
            return None
    
    def parse_adjustment_info(self, html):
        """解析油价调整信息"""
        try:
            trend = {
                "direction": "stable",
                "amount": 0,
                "description": "价格稳定"
            }
            
            # 匹配调整信息
            adjustment_match = re.search(r'下次油价.*?(\d+月\d+日\d+时调整)', html)
            next_adjustment = adjustment_match.group(1) if adjustment_match else None
            
            # 匹配趋势信息
            trend_up = re.search(r'预计上调.*?([\d.]+)元', html)
            trend_down = re.search(r'预计下调.*?([\d.]+)元', html)
            
            if trend_up:
                amount = float(trend_up.group(1))
                trend = {
                    "direction": "up",
                    "amount": amount,
                    "description": f"预计上调{amount}元/升"
                }
            elif trend_down:
                amount = float(trend_down.group(1))
                trend = {
                    "direction": "down", 
                    "amount": amount,
                    "description": f"预计下调{amount}元/升"
                }
            
            return {
                "next_adjustment": next_adjustment,
                "trend": trend
            }
            
        except Exception:
            return {
                "next_adjustment": None,
                "trend": {
                    "direction": "stable", 
                    "amount": 0,
                    "description": "价格稳定"
                }
            }
    
    def _create_error_data(self, province_name, province_code, error_message):
        """创建错误数据"""
        return {
            "status": "error",
            "name": province_name,
            "code": province_code,
            "error": {
                "code": "FETCH_FAILED",
                "message": error_message,
                "retry_after": datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
            },
            "update_time": datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
        }
    
    def _create_final_output(self, all_data, success_count):
        """创建最终输出"""
        total_provinces = len(self.provinces)
        status = "success" if success_count > 0 else "error"
        if 0 < success_count < total_provinces:
            status = "partial_success"
        
        return {
            "status": status,
            "last_updated": datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            "data_source": "www.qiyoujiage.com",
            "version": "1.0",
            "statistics": {
                "total_provinces": total_provinces,
                "success_count": success_count,
                "error_count": total_provinces - success_count,
                "success_rate": round(success_count / total_provinces * 100, 2)
            },
            "data": all_data
        }

def main():
    """主函数"""
    print("🚀 开始抓取中国各省油价数据...")
    print(f"📋 总共 {len(ChinaOilPriceAPI().provinces)} 个省份")
    
    api = ChinaOilPriceAPI()
    result = api.fetch_all_prices()
    
    # 保存数据
    with open('oil_prices.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 数据抓取完成！")
    print(f"📊 成功: {result['statistics']['success_count']}/{result['statistics']['total_provinces']}")
    print(f"📈 成功率: {result['statistics']['success_rate']}%")
    print(f"💾 数据已保存至: oil_prices.json")

if __name__ == '__main__':
    main()