#!/usr/bin/env python3
"""
中国油价数据抓取脚本 - aiohttp异步极速版
"""

import aiohttp
import asyncio
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
import re

class ChinaOilPriceAPI:
    def __init__(self, max_concurrent=20):
        with open('provinces.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.provinces = config['provinces']
        self.max_concurrent = max_concurrent  # 控制并发量
        self.connector = None

    async def __aenter__(self):
        # 创建TCP连接器，复用连接，限制总连接数
        self.connector = aiohttp.TCPConnector(limit=self.max_concurrent, limit_per_host=5)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.connector:
            await self.connector.close()

    async def fetch_all_prices(self):
        """异步并发抓取所有省份油价数据"""
        print("🚀 启动aiohttp异步抓取中国各省油价数据...")
        print(f"📋 省份总数: {len(self.provinces)}, 并发数: {self.max_concurrent}")
        
        start_time = datetime.now()
        all_data = {}
        success_count = 0
        
        # 为每个省份创建异步任务
        async with aiohttp.ClientSession(connector=self.connector) as session:
            tasks = [
                self.fetch_province_price(session, province_name, province_code)
                for province_name, province_code in self.provinces.items()
            ]
            
            # 等待所有任务完成并收集结果
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            for province_name, result in zip(self.provinces.keys(), results):
                if isinstance(result, Exception):
                    error_msg = f"异步任务异常: {str(result)}"
                    all_data[province_name] = self._create_error_data(province_name, "", error_msg)
                    print(f"💥 {province_name}: {error_msg}")
                else:
                    all_data[province_name] = result
                    if result['status'] == 'success':
                        success_count += 1
                        prices = result['prices']
                        print(f"✅ {province_name}: 92#{prices['92']} 95#{prices['95']} 98#{prices['98']} 0#{prices['0']}")
                    else:
                        print(f"❌ {province_name}: {result['error']}")
        
        duration = (datetime.now() - start_time).total_seconds()
        print(f"\n⏱️ 异步抓取总耗时: {duration:.2f}秒")
        
        return self._create_final_output(all_data, success_count)
    
    async def fetch_province_price(self, session, province_name, province_code):
        """异步抓取单个省份油价数据"""
        try:
            url = f'http://www.qiyoujiage.com/{province_code}.shtml'
            
            # 发送异步GET请求
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    return self._create_error_data(province_name, province_code, f"HTTP状态码: {response.status}")
                
                html = await response.text()
                doc = BeautifulSoup(html, 'html.parser')
                
                # 解析油价数据
                entries = {}
                oil_elements = doc.select('#youjia > dl')
                
                for dl in oil_elements:
                    dt_element = dl.select_one('dt')
                    dd_element = dl.select_one('dd')
                    
                    if dt_element and dd_element:
                        oil_type_text = dt_element.get_text().strip()
                        price_value = dd_element.get_text().strip()
                        
                        if '92#' in oil_type_text:
                            entries['92'] = self._parse_price(price_value)
                        elif '95#' in oil_type_text:
                            entries['95'] = self._parse_price(price_value)
                        elif '98#' in oil_type_text:
                            entries['98'] = self._parse_price(price_value)
                        elif '0#' in oil_type_text or '柴油' in oil_type_text:
                            entries['0'] = self._parse_price(price_value)
                
                # 解析调整信息
                adjustment_info = self._parse_adjustment_info(doc)
                
                # 构建价格数据
                prices = {
                    '92': entries.get('92', 0),
                    '95': entries.get('95', 0),
                    '98': entries.get('98', 0),
                    '0': entries.get('0', 0)
                }
                
                # 检查是否获取到有效数据
                valid_prices = any(price > 0 for price in prices.values())
                if not valid_prices:
                    return self._create_error_data(province_name, province_code, "未解析到油价数据")
                
                return {
                    "status": "success",
                    "name": province_name,
                    "prices": prices,
                    "next_adjustment": adjustment_info.get('next_adjustment'),
                    "trend": adjustment_info.get('trend'),
                    "update_time": datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
                }
                
        except asyncio.TimeoutError:
            return self._create_error_data(province_name, province_code, "请求超时")
        except aiohttp.ClientError as e:
            return self._create_error_data(province_name, province_code, f"网络请求失败: {str(e)}")
        except Exception as e:
            return self._create_error_data(province_name, province_code, f"解析异常: {str(e)}")
    
    def _parse_price(self, price_text):
        """解析价格文本为浮点数"""
        try:
            numeric_match = re.search(r'([\d.]+)', price_text)
            return float(numeric_match.group(1)) if numeric_match else 0
        except:
            return 0
    
    def _parse_adjustment_info(self, doc):
        """解析油价调整信息"""
        try:
            adjustment_divs = doc.select('#youjiaCont > div')
            for div in adjustment_divs:
                div_text = div.get_text().strip()
                
                time_match = re.search(r'下次油价(\d+月\d+日\d+时调整)', div_text)
                if time_match:
                    next_adjustment = time_match.group(0)
                    
                    trend_match = re.search(r'目前预计(上调|下调)油价.*?\(([\d.]+)元/升', div_text)
                    if trend_match:
                        direction = "up" if trend_match.group(1) == "上调" else "down"
                        amount = float(trend_match.group(2))
                        trend_desc = "上调" if direction == "up" else "下调"
                        
                        return {
                            "next_adjustment": next_adjustment,
                            "trend": {
                                "direction": direction,
                                "amount": amount,
                                "description": f"预计{trend_desc}{amount}元/升"
                            }
                        }
            
            return {
                "next_adjustment": None,
                "trend": {
                    "direction": "stable", 
                    "amount": 0,
                    "description": "价格稳定"
                }
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
            "error": error_message,
            "update_time": datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
        }
    
    def _create_final_output(self, all_data, success_count):
        """创建最终输出"""
        total_provinces = len(self.provinces)
        
        return {
            "status": "success" if success_count > 0 else "error",
            "last_updated": datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            "data_source": "www.qiyoujiage.com",
            "version": "3.0",
            "statistics": {
                "total": total_provinces,
                "success": success_count,
                "error": total_provinces - success_count,
                "rate": round(success_count / total_provinces * 100, 1)
            },
            "data": all_data
        }

async def main():
    """主异步函数"""
    start_time = datetime.now()
    print(f"⏰ 开始时间: {start_time.strftime('%H:%M:%S')}")
    
    # 使用异步上下文管理器，控制并发数为15
    async with ChinaOilPriceAPI(max_concurrent=15) as api:
        result = await api.fetch_all_prices()
    
    # 保存数据
    with open('oil_prices.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"\n✅ 数据抓取完成!")
    print(f"📊 统计: {result['statistics']['success']}/{result['statistics']['total']} 成功")
    print(f"📈 成功率: {result['statistics']['rate']}%")
    print(f"⏱️ 总耗时: {duration:.2f}秒")
    print(f"💾 数据已保存至: oil_prices.json")
    
    # 显示成功省份的数据样例
    print("\n📋 成功省份样例:")
    success_provinces = [name for name, data in result['data'].items() if data['status'] == 'success']
    for province in success_provinces[:5]:
        data = result['data'][province]
        prices = data['prices']
        print(f"  {province}: 92#{prices['92']} 95#{prices['95']} 98#{prices['98']} 0#{prices['0']}")

if __name__ == '__main__':
    # 运行异步主函数
    asyncio.run(main())