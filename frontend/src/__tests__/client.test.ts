import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as clientModule from '../api/client'

vi.mock('axios', () => {
  const mockAxiosInstance = vi.fn(() => ({
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  }))
  return {
    default: Object.assign(mockAxiosInstance, {
      create: vi.fn(() => mockAxiosInstance()),
    }),
    create: vi.fn(() => mockAxiosInstance()),
  }
})

beforeEach(() => {
  vi.clearAllMocks()
})

describe('configApi', () => {
  it('has required methods', () => {
    expect(typeof clientModule.configApi.getAll).toBe('function')
    expect(typeof clientModule.configApi.get).toBe('function')
    expect(typeof clientModule.configApi.set).toBe('function')
    expect(typeof clientModule.configApi.delete).toBe('function')
    expect(typeof clientModule.configApi.testConnection).toBe('function')
  })
})

describe('documentsApi', () => {
  it('has required methods', () => {
    expect(typeof clientModule.documentsApi.process).toBe('function')
    expect(typeof clientModule.documentsApi.trigger).toBe('function')
    expect(typeof clientModule.documentsApi.testConnection).toBe('function')
    expect(typeof clientModule.documentsApi.getTagged).toBe('function')
    expect(typeof clientModule.documentsApi.getTags).toBe('function')
    expect(typeof clientModule.documentsApi.getChatList).toBe('function')
    expect(typeof clientModule.documentsApi.getChatDocument).toBe('function')
    expect(typeof clientModule.documentsApi.chat).toBe('function')
    expect(typeof clientModule.documentsApi.searchPaperless).toBe('function')
    expect(typeof clientModule.documentsApi.getPreview).toBe('function')
  })
})

describe('statsApi', () => {
  it('has required methods', () => {
    expect(typeof clientModule.statsApi.get).toBe('function')
    expect(typeof clientModule.statsApi.getDaily).toBe('function')
    expect(typeof clientModule.statsApi.getRecent).toBe('function')
    expect(typeof clientModule.statsApi.reset).toBe('function')
  })
})

describe('schedulerApi', () => {
  it('has required methods', () => {
    expect(typeof clientModule.schedulerApi.getStatus).toBe('function')
    expect(typeof clientModule.schedulerApi.start).toBe('function')
    expect(typeof clientModule.schedulerApi.stop).toBe('function')
    expect(typeof clientModule.schedulerApi.update).toBe('function')
    expect(typeof clientModule.schedulerApi.triggerNow).toBe('function')
    expect(typeof clientModule.schedulerApi.clearState).toBe('function')
  })
})
