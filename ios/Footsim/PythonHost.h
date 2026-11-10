#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// The embedded Python that runs the game's server (footsim.phone.main).
@interface PythonHost : NSObject

/// Start Python on a thread of its own and serve the game. Set the FOOTSIM_* environment
/// first. Returns at once; ``failure`` is called (on any thread) if Python can't start or the
/// server stops with an error.
+ (void)startWithFailure:(void (^)(NSString *message))failure;

/// Run a line of Python from any thread (it takes the interpreter lock). NO if it raised.
+ (BOOL)run:(NSString *)code;

@end

NS_ASSUME_NONNULL_END
