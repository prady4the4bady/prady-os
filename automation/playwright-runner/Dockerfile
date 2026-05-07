FROM mcr.microsoft.com/playwright:v1.52.0-noble

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY src/ src/

EXPOSE 3000

CMD ["npm", "start"]
