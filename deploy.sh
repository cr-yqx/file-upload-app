#!/bin/bash

# Railway 快速部署脚本

echo "🚀 开始准备 Railway 部署..."

# 检查是否已初始化 Git
if [ ! -d .git ]; then
    echo "📦 初始化 Git 仓库..."
    git init
    echo "✅ Git 仓库初始化完成"
else
    echo "✅ Git 仓库已存在"
fi

# 添加所有文件
echo "📝 添加文件到 Git..."
git add .

# 提交
echo "💾 提交更改..."
git commit -m "Prepare for Railway deployment" || echo "没有新的更改需要提交"

echo ""
echo "✅ 部署准备完成！"
echo ""
echo "📋 下一步操作："
echo "1. 在 GitHub 创建新仓库"
echo "2. 运行以下命令推送代码："
echo ""
echo "   git remote add origin https://github.com/你的用户名/仓库名.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "3. 访问 https://railway.app/ 并从 GitHub 部署"
echo ""
echo "📖 详细步骤请查看 RAILWAY部署指南.md"
