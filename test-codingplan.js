#!/usr/bin/env node

/**
 * MiniMax CodingPlan 测试脚本
 * 用于测试 VSCode 中的 MiniMax API 连接和基本功能
 */

const fs = require('fs');
const path = require('path');
const https = require('https');

// 配置颜色输出
const colors = {
    reset: '\x1b[0m',
    green: '\x1b[32m',
    red: '\x1b[31m',
    yellow: '\x1b[33m',
    blue: '\x1b[34m',
    magenta: '\x1b[35m',
    cyan: '\x1b[36m'
};

function log(color, message) {
    console.log(`${colors[color]}${message}${colors.reset}`);
}

// 读取环境变量配置
function loadConfig() {
    const configFiles = ['.env.local', '.env', '.env.example'];
    let config = {};
    
    for (const file of configFiles) {
        const filePath = path.join(__dirname, file);
        if (fs.existsSync(filePath)) {
            log('cyan', `📖 正在读取配置文件: ${file}`);
            const content = fs.readFileSync(filePath, 'utf8');
            
            content.split('\n').forEach(line => {
                const [key, value] = line.split('=');
                if (key && value && key.includes('MINIMAX')) {
                    config[key.trim()] = value.trim();
                }
            });
            
            if (config.MINIMAX_API_KEY) {
                log('green', `✅ 找到 MiniMax API 配置`);
                break;
            }
        }
    }
    
    // 检查环境变量
    if (!config.MINIMAX_API_KEY && process.env.MINIMAX_API_KEY) {
        config.MINIMAX_API_KEY = process.env.MINIMAX_API_KEY;
        log('green', `✅ 从环境变量获取 MiniMax API 密钥`);
    }
    
    return config;
}

// 测试 MiniMax API 连接
function testMiniMaxConnection(apiKey) {
    return new Promise((resolve, reject) => {
        log('blue', '🔄 正在测试 MiniMax API 连接...');
        
        const postData = JSON.stringify({
            model: 'abab6.5s-chat',
            messages: [
                {
                    role: 'user',
                    content: '你好，这是一个连接测试。请简单回复"连接成功"。'
                }
            ],
            max_tokens: 50,
            temperature: 0.1
        });
        
        const options = {
            hostname: 'api.minimax.chat',
            port: 443,
            path: '/v1/text/chatcompletion_v2',
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${apiKey}`,
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(postData)
            }
        };
        
        const req = https.request(options, (res) => {
            let data = '';
            
            res.on('data', (chunk) => {
                data += chunk;
            });
            
            res.on('end', () => {
                try {
                    const response = JSON.parse(data);
                    
                    if (res.statusCode === 200 && response.choices && response.choices.length > 0) {
                        const reply = response.choices[0].message.content;
                        log('green', `✅ MiniMax API 连接成功！`);
                        log('cyan', `📝 回复内容: ${reply}`);
                        resolve({
                            success: true,
                            reply: reply,
                            usage: response.usage
                        });
                    } else {
                        log('red', `❌ API 响应异常: ${JSON.stringify(response, null, 2)}`);
                        reject(new Error(`API 错误: ${response.error?.message || '未知错误'}`));
                    }
                } catch (e) {
                    log('red', `❌ 解析响应失败: ${e.message}`);
                    log('yellow', `原始响应: ${data}`);
                    reject(e);
                }
            });
        });
        
        req.on('error', (e) => {
            log('red', `❌ 网络连接失败: ${e.message}`);
            reject(e);
        });
        
        req.write(postData);
        req.end();
        
        // 设置超时
        req.setTimeout(30000, () => {
            log('red', '❌ 请求超时 (30秒)');
            req.destroy();
            reject(new Error('请求超时'));
        });
    });
}

// 测试代码生成功能
function testCodeGeneration(apiKey) {
    return new Promise((resolve, reject) => {
        log('blue', '🔄 正在测试代码生成功能...');
        
        const postData = JSON.stringify({
            model: 'abab6.5s-chat',
            messages: [
                {
                    role: 'user',
                    content: '请生成一个简单的 Python 函数，用于计算两个数的和。'
                }
            ],
            max_tokens: 200,
            temperature: 0.3
        });
        
        const options = {
            hostname: 'api.minimax.chat',
            port: 443,
            path: '/v1/text/chatcompletion_v2',
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${apiKey}`,
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(postData)
            }
        };
        
        const req = https.request(options, (res) => {
            let data = '';
            
            res.on('data', (chunk) => {
                data += chunk;
            });
            
            res.on('end', () => {
                try {
                    const response = JSON.parse(data);
                    
                    if (res.statusCode === 200 && response.choices && response.choices.length > 0) {
                        const code = response.choices[0].message.content;
                        log('green', `✅ 代码生成功能测试成功！`);
                        log('cyan', `📝 生成的代码:\n${code}`);
                        resolve({
                            success: true,
                            code: code,
                            usage: response.usage
                        });
                    } else {
                        reject(new Error(`代码生成失败: ${response.error?.message || '未知错误'}`));
                    }
                } catch (e) {
                    reject(e);
                }
            });
        });
        
        req.on('error', (e) => {
            reject(e);
        });
        
        req.write(postData);
        req.end();
        
        req.setTimeout(30000, () => {
            req.destroy();
            reject(new Error('代码生成请求超时'));
        });
    });
}

// 主测试函数
async function runTests() {
    log('magenta', '🎉 MiniMax CodingPlan VSCode 集成测试');
    log('magenta', '='.repeat(50));
    
    try {
        // 1. 加载配置
        log('blue', '📋 第1步: 加载配置文件...');
        const config = loadConfig();
        
        if (!config.MINIMAX_API_KEY || config.MINIMAX_API_KEY === 'your-api-key-here') {
            log('red', '❌ 未找到有效的 MiniMax API 密钥');
            log('yellow', '💡 请确保已经配置了正确的 API 密钥:');
            log('yellow', '   方式1: 设置环境变量 MINIMAX_API_KEY');
            log('yellow', '   方式2: 在 .env.local 文件中配置');
            log('yellow', '   方式3: 在 .env.example 文件中替换占位符');
            return;
        }
        
        const apiKey = config.MINIMAX_API_KEY;
        log('green', `✅ API 密钥已加载 (${apiKey.substring(0, 8)}...)`);
        
        // 2. 测试基本连接
        log('blue', '🔗 第2步: 测试 API 连接...');
        const connectionResult = await testMiniMaxConnection(apiKey);
        
        if (connectionResult.usage) {
            log('cyan', `📊 使用情况: ${JSON.stringify(connectionResult.usage)}`);
        }
        
        // 3. 测试代码生成
        log('blue', '💻 第3步: 测试代码生成功能...');
        const codeResult = await testCodeGeneration(apiKey);
        
        if (codeResult.usage) {
            log('cyan', `📊 代码生成使用情况: ${JSON.stringify(codeResult.usage)}`);
        }
        
        // 4. 总结
        log('green', '🎉 所有测试通过！');
        log('magenta', '='.repeat(50));
        log('green', '✅ MiniMax CodingPlan 已成功配置并可在 VSCode 中使用');
        log('cyan', '💡 现在您可以在 VSCode 中使用 MiniMax 进行代码生成、优化和分析');
        
    } catch (error) {
        log('red', `❌ 测试失败: ${error.message}`);
        log('yellow', '🔧 请检查以下事项:');
        log('yellow', '   1. API 密钥是否正确');
        log('yellow', '   2. 网络连接是否正常');
        log('yellow', '   3. MiniMax 服务是否可用');
    }
}

// 检查是否直接运行此脚本
if (require.main === module) {
    runTests();
}

module.exports = {
    loadConfig,
    testMiniMaxConnection,
    testCodeGeneration,
    runTests
};