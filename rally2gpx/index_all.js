const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-extra');
const { buildGPX, BaseBuilder } = require('gpx-builder');
const { Point, Metadata, Person } = BaseBuilder.MODELS;

puppeteer.use(require('puppeteer-extra-plugin-stealth')());

const showHelp = function () {
  const bin = path.basename(process.argv[1]);
  console.log(`Usage: node ${bin} URL OUTDIR`);
};

const sanitizeFilename = function (name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+/, '')
    .replace(/-+$/, '') || 'stage';
};

const generateGPX = function (stage, outDir) {
  if (!Array.isArray(stage.coordinates) || stage.coordinates.length === 0) {
    return false;
  }

  const points = [];
  const gpxData = new BaseBuilder();

  for (let i = 0; i < stage.coordinates.length; i++) {
    points.push(new Point(stage.coordinates[i][1], stage.coordinates[i][0]));
  }

  gpxData.setMetadata(new Metadata({
    name: stage.short,
    desc: `WRC track extracted for stage ${stage.name}`,
    author: new Person({
      name: 'crazyfacka'
    })
  }));

  gpxData.setSegmentPoints(points);

  const safeName = sanitizeFilename(stage.short || stage.name || 'stage');
  const filename = `${safeName}.gpx`;
  const outputPath = path.join(outDir, filename);

  fs.writeFileSync(outputPath, buildGPX(gpxData.toObject()), 'utf8');
  console.log(`✅ GPX: ${outputPath}`);
  return true;
};

async function scrapePage(url) {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  page.setDefaultTimeout(120000);
  page.setDefaultNavigationTimeout(120000);

  await page.setViewport({ width: 1080, height: 1024 });

  // Navigate (slow/limited environments like Docker/Render can need more time)
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 120000 });

  // Cookie banner (best-effort)
  try {
    await page.waitForSelector('.fc-cta-consent', { timeout: 5000 });
    await page.click('.fc-cta-consent');
  } catch (e) {}

  // Cookie banner "Accept All" (best-effort)
  try {
    await page.waitForSelector('.cm__body', { timeout: 5000 });
    await page.click('.cm__btn >>> ::-p-text(Accept All)');
  } catch (e) {}

  // Wait for the map to be ready (be generous with timeouts)
  await page.waitForSelector('.leaflet-control-container', { timeout: 120000 });
  await page.waitForNetworkIdle({ idleTime: 1000, timeout: 120000 });
  await page.waitForFunction('window?.sl?.leaflet?.data?.storage?.stages', { timeout: 120000 });

  const stages = await page.evaluate(() => {
    function flattenStages() {
      const simpleStages = [];
      for (let i = 0; i < sl.leaflet.data.storage.stages.length; i++) {
        const curStage = sl.leaflet.data.storage.stages[i];
        let coordinates;
        for (let j = 0; j < curStage.geometries.length; j++) {
          if (curStage.geometries[j].type === 'SL' || curStage.geometries[j].type === 'PL') {
            coordinates = curStage.geometries[j].geometry.coordinates;
          }
        }
        simpleStages[i] = {
          value: i,
          name: curStage.fullName,
          short: curStage.name,
          coordinates: coordinates
        };
      }
      return simpleStages;
    }
    return flattenStages();
  });

  await browser.close();

  return stages;
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length !== 2) {
    showHelp();
    process.exit(1);
  }

  const [url, outDir] = args;
  fs.mkdirSync(outDir, { recursive: true });

  console.log(`Downloading and parsing data from '${url}'`);
  const stages = await scrapePage(url);

  let generated = 0;
  for (const stage of stages) {
    try {
      if (generateGPX(stage, outDir)) {
        generated++;
      }
    } catch (err) {
      console.error(`Error generating GPX for stage ${stage.name}:`, err.message);
    }
  }

  if (generated === 0) {
    console.error('No GPX files were generated.');
    process.exit(1);
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
