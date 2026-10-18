/* Librairie Mobile - État global partagé centralisé */
'use strict';
import { USER_KEY } from './core.js';

export function getAutoMobileMoment() {
  const isSunday = new Date().getDay() === 0;
  const currentHour = new Date().getHours();
  return isSunday ? (currentHour >= 12 ? '2e Culte (Jeunes EJP)' : '1er Culte (Principal)') : 'En semaine / Autre';
}

export const state = {
  currentUser: localStorage.getItem(USER_KEY) || '',
  currentMode: 'sale', // 'sale' | 'recv'
  cart: [],            // [{ book, qty, lot }]
  recvList: [],        // [{ book, qty }]
  ownersList: [],
  payOptions: [],
  originPayments: {},  // { [owner]: { method, parts } }
  mGender: '',
  mAge: '',
  mStar: 0,
  mMoment: getAutoMobileMoment(),
  users: [],
  pendingNewCode: null,
  currentMatchedBook: null,
  isNetworkOnline: true,
  pingFailCount: 0,
  dbAuthors: [],
  dbPublishers: [],
  currentUpsellContext: null,
  activeMpOwner: null,
  activeMpTotal: 0,
  mpMode1: 'Espèces',
  mpMode2: 'CB',
  isLookingUp: false
};
