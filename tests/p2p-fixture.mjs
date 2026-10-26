import { createRelay } from '../server/index.mjs';
import { writeFileSync } from 'node:fs';
const relay=createRelay({enrollmentToken:process.env.CAMPUSLINK_TEST_TOKEN});
relay.server.listen(0,'127.0.0.1',()=>{console.log(JSON.stringify({port:relay.server.address().port}));});
const snapshot=setInterval(()=>writeFileSync(process.env.CAMPUSLINK_TEST_METRICS,JSON.stringify(relay.broker.metrics)),100);
process.on('SIGINT',async()=>{clearInterval(snapshot);await relay.close();process.exit(0);});
