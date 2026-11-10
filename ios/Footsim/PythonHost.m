#import "PythonHost.h"
#import <Python/Python.h>

@implementation PythonHost

static BOOL started = NO;

+ (void)startWithFailure:(void (^)(NSString *message))failure {
    NSThread *thread = [[NSThread alloc] initWithBlock:^{
        NSString *error = [self serve];
        if (error != nil) {
            NSLog(@"footsim: %@", error);
            failure(error);
        }
    }];
    thread.name = @"footsim.python";
    thread.stackSize = 16 * 1024 * 1024;  // the main thread's default; secondary threads get 512 KB
    thread.qualityOfService = NSQualityOfServiceUserInitiated;
    [thread start];
}

/// Initialise Python as the docs say for an embedded iOS app ("Using Python on iOS"), then
/// run the server. Returns only on failure.
+ (nullable NSString *)serve {
    NSString *resources = [[NSBundle mainBundle] resourcePath];
    PyPreConfig preconfig;
    PyConfig config;
    PyPreConfig_InitIsolatedConfig(&preconfig);
    PyConfig_InitIsolatedConfig(&config);
    preconfig.utf8_mode = 1;
    config.buffered_stdio = 0;
    config.write_bytecode = 0;  // the bundle is read-only
    config.install_signal_handlers = 0;
    config.use_environment = 0;

    PyStatus status = Py_PreInitialize(&preconfig);
    if (PyStatus_Exception(status)) {
        return [NSString stringWithFormat:@"Python pre-init failed: %s", status.err_msg];
    }
    wchar_t *home = Py_DecodeLocale([[resources stringByAppendingPathComponent:@"python"] UTF8String], NULL);
    status = PyConfig_SetString(&config, &config.home, home);
    PyMem_RawFree(home);
    if (PyStatus_Exception(status)) {
        PyConfig_Clear(&config);
        return [NSString stringWithFormat:@"Python home failed: %s", status.err_msg];
    }
    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) {
        return [NSString stringWithFormat:@"Python init failed: %s", status.err_msg];
    }
    started = YES;

    // The packages, then the game itself (laid out as in the repository, so its paths hold).
    NSString *boot = [NSString stringWithFormat:
        @"import site, sys, traceback\n"
         "site.addsitedir(%@)\n"
         "sys.path.insert(0, %@)\n"
         "try:\n"
         "    from footsim.phone.main import main\n"
         "    main()\n"
         "except BaseException:\n"
         "    sys.footsim_error = traceback.format_exc()\n"
         "    print(sys.footsim_error, file=sys.stderr)\n"
         "    raise\n",
        [self literal:[resources stringByAppendingPathComponent:@"app_packages"]],
        [self literal:[resources stringByAppendingPathComponent:@"app/backend/src"]]];
    int failed = PyRun_SimpleString([boot UTF8String]);
    if (!failed) {
        PyEval_SaveThread();
        return @"the game's server stopped";
    }
    NSString *message = @"the game's server failed to start";
    PyObject *sys = PyImport_ImportModule("sys");
    PyObject *text = sys ? PyObject_GetAttrString(sys, "footsim_error") : NULL;
    if (text != NULL && PyUnicode_Check(text)) {
        message = [NSString stringWithUTF8String:PyUnicode_AsUTF8(text)];
    }
    PyErr_Clear();
    Py_XDECREF(text);
    Py_XDECREF(sys);
    PyEval_SaveThread();  // this thread is done: leave the interpreter free for +run:
    return message;
}

+ (NSString *)literal:(NSString *)path {
    NSString *escaped = [[path stringByReplacingOccurrencesOfString:@"\\" withString:@"\\\\"]
                         stringByReplacingOccurrencesOfString:@"'" withString:@"\\'"];
    return [NSString stringWithFormat:@"'%@'", escaped];
}

+ (BOOL)run:(NSString *)code {
    if (!started) {
        return NO;
    }
    PyGILState_STATE state = PyGILState_Ensure();
    int failed = PyRun_SimpleString([code UTF8String]);
    PyGILState_Release(state);
    return failed == 0;
}

@end
